import hashlib
import hmac
import ipaddress
import json
import time
import uuid
from datetime import timezone

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate, now_datetime

from purchase_integration.integration import canonical_json, get_settings, sign


def _as_datetime(value):
    if not value:
        return None
    parsed = get_datetime(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _as_date(value):
    if not value:
        return None
    return getdate(_as_datetime(value) or value)


def _media_type(value):
    raw = (value or "DOCUMENT").strip().upper()
    if raw in ("IMAGE", "IMG", "PHOTO"):
        return "IMAGE"
    if raw in ("VIDEO", "VID"):
        return "VIDEO"
    return "DOCUMENT"


def _line_qty(line):
    for fieldname in ("requested_purchase_quantity", "purchase_required_qty", "quantity"):
        if line.get(fieldname) is not None:
            return flt(line.get(fieldname))
    return 0.0


def _payload_and_raw(payload=None, **kwargs):
    raw = frappe.request.get_data(cache=True, as_text=True) if getattr(frappe, "request", None) else ""
    if payload:
        data = json.loads(payload) if isinstance(payload, str) else payload
    elif kwargs:
        data = kwargs
    elif raw:
        data = json.loads(raw)
    else:
        frappe.throw(_("A JSON payload is required."))
    return data, raw or canonical_json(data)


def _source_ip_allowed(settings):
    allowed = [value.strip() for value in (settings.allowed_source_ips or "").split(",") if value.strip()]
    if not allowed:
        return True
    source = frappe.local.request_ip
    return any(ipaddress.ip_address(source) in ipaddress.ip_network(network, strict=False) for network in allowed)


def _authenticate(settings, raw):
    if not settings.integration_enabled:
        frappe.throw(_("K95 Purchase Integration is disabled."), frappe.PermissionError)
    if not _source_ip_allowed(settings):
        frappe.throw(_("Source IP is not allowed."), frappe.PermissionError)
    if settings.inbound_auth_type != "HMAC-SHA256":
        # ERPNext API-token authentication is handled by Frappe before this method.
        if frappe.session.user == "Guest":
            frappe.throw(_("ERPNext API authentication is required."), frappe.AuthenticationError)
        return
    key = frappe.get_request_header("X-K95-Key")
    timestamp = frappe.get_request_header("X-K95-Timestamp")
    supplied = frappe.get_request_header("X-K95-Signature")
    if not key or not timestamp or not supplied or key != settings.inbound_key_id:
        frappe.throw(_("Invalid K95 authentication headers."), frappe.AuthenticationError)
    try:
        if abs(int(time.time()) - int(timestamp)) > int(settings.replay_window_seconds or 300):
            frappe.throw(_("The K95 request timestamp is outside the replay window."), frappe.AuthenticationError)
    except ValueError:
        frappe.throw(_("Invalid K95 timestamp."), frappe.AuthenticationError)
    secret = settings.get_password("inbound_hmac_secret")
    expected = sign(secret, "POST", frappe.request.path, timestamp, raw)
    if not secret or not hmac.compare_digest(expected, supplied):
        frappe.throw(_("Invalid K95 request signature."), frappe.AuthenticationError)


def _normalize(data):
    request = data.get("purchase_request") or data.get("data") or data
    lines = request.get("lines") or request.get("items") or []
    external_pr_id = request.get("external_pr_id") or request.get("pr_id") or request.get("id")
    if not external_pr_id:
        frappe.throw(_("external_pr_id is required."))
    eligible = []
    for index, line in enumerate(lines, 1):
        if line.get("send_to_erpnext") is False:
            continue
        if line.get("store_decision") and line.get("store_decision") != "Purchase Required":
            continue
        line = dict(line)
        line["external_line_id"] = line.get("external_line_id") or line.get("line_id") or f"{external_pr_id}-L{index:03d}"
        line["_purchase_qty"] = _line_qty(line)
        if line["_purchase_qty"] <= 0:
            frappe.throw(
                _("Line {0}: purchase quantity must be greater than 0.").format(line["external_line_id"]),
                frappe.ValidationError,
            )
        eligible.append(line)
    if not eligible:
        frappe.throw(_("No Purchase Required lines were supplied."))
    return request, eligible, external_pr_id


def _build_nimr_document(settings, data, request, lines, external_pr_id, event):
    requester = request.get("requester") or {}
    doc = frappe.get_doc({
        "doctype": "New Item Material Request", "external_pr_id": external_pr_id,
        "external_document_id": request.get("document_id"), "correlation_id": data.get("correlation_id"),
        "source_event_id": event.event_id, "source_event_version": str(data.get("event_version") or 1),
        "source_record_version": request.get("record_version") or 1, "idempotency_key": event.idempotency_key,
        "company": request.get("company") or settings.company, "request_title": request.get("title") or request.get("pr_number"),
        "priority": request.get("priority") or "Medium", "request_date": _as_datetime(request.get("request_date")),
        "submitted_at": _as_datetime(request.get("submitted_at")), "requester_user_id": requester.get("user_id"),
        "requester_employee_id": requester.get("employee_id"), "requester_name": requester.get("name"),
        "requester_email": requester.get("email"), "department_name": request.get("department"),
        "requested_on_behalf_of": request.get("requested_on_behalf_of"), "received_at": now_datetime(),
        "integration_status": "Processing", "source_payload_hash": event.payload_hash, "inbound_event": event.name,
    })
    for index, line in enumerate(lines, 1):
        qty = line.get("_purchase_qty") if line.get("_purchase_qty") is not None else _line_qty(line)
        requested_qty = flt(line.get("quantity")) if line.get("quantity") is not None else qty
        erpnext_item = line.get("erpnext_item_code")
        if erpnext_item and not frappe.db.exists("Item", {"name": erpnext_item, "disabled": 0}):
            frappe.throw(_("Line {0}: ERPNext Item {1} does not exist or is disabled.").format(line["external_line_id"], erpnext_item))
        purchase_uom = None
        if erpnext_item:
            requested_uom = line.get("uom")
            purchase_uom = requested_uom if requested_uom and frappe.db.exists("UOM", requested_uom) else frappe.db.get_value("Item", erpnext_item, "stock_uom")
        doc.append("items", {
            "external_line_id": line["external_line_id"], "line_number": line.get("line_number") or index,
            "item_source": line.get("item_source") or ("MASTER" if erpnext_item else "NEW"),
            "external_item_code": line.get("k95_item_code") or line.get("item_code"),
            "k95_item_id": line.get("k95_item_id"), "requested_item_name": line.get("item_name") or line.get("name"),
            "requested_description": line.get("description"), "requirement": line.get("requirement"),
            "need_purpose": line.get("need_purpose"), "requested_qty": requested_qty,
            "purchase_required_qty": qty, "final_purchase_qty": qty,
            "requested_uom": line.get("uom"), "purchase_uom": purchase_uom,
            "requested_required_by": _as_date(line.get("required_by")), "schedule_date": _as_date(line.get("required_by")),
            "purchase_description": line.get("description"), "purchase_remarks": line.get("remarks"),
            "primary_image": line.get("primary_image_url"), "erpnext_item": erpnext_item,
            "item_resolution_status": "MANUALLY_MATCHED" if erpnext_item else "PENDING_ITEM_CREATION",
            "processing_status": "READY_FOR_MR" if erpnext_item else "PENDING_ITEM_VERIFICATION",
            "resolution_method": "ERPNEXT_ITEM_CODE" if erpnext_item else None,
        })
    for attachment in request.get("attachments") or []:
        doc.append("attachments", {
            "external_attachment_id": attachment.get("attachment_id") or attachment.get("id"),
            "external_line_id": attachment.get("line_id"), "media_type": _media_type(attachment.get("media_type")),
            "file_name": attachment.get("file_name"), "mime_type": attachment.get("mime_type"),
            "file_size": attachment.get("file_size"), "file_hash": attachment.get("sha256"),
            "external_file_url": attachment.get("url"), "caption": attachment.get("caption"),
            "is_primary_image": attachment.get("is_primary_image") or 0,
        })
    return doc


def _response(nimr, duplicate=False):
    doc = frappe.get_doc("New Item Material Request", nimr)
    return {
        "success": True,
        "duplicate": duplicate,
        "nimr": doc.name,
        "external_pr_id": doc.external_pr_id,
        "processing_status": doc.processing_status,
        "lines": [{
            "line_id": row.external_line_id,
            "k95_item_id": row.k95_item_id,
            "erpnext_item_code": row.erpnext_item,
            "item_resolution_status": row.item_resolution_status,
        } for row in doc.items],
    }


def _fail_inbound_event(event, external_pr_id, line_ids, exc):
    clear_text = _("NIMR intake failed for {0}, line(s) {1}: {2}").format(
        external_pr_id or "unknown PR", ", ".join(line_ids) or "unknown", str(exc)
    )
    frappe.db.set_value("K95 Inbound Event", event.name, {
        "status": "FAILED", "last_error": clear_text[:10000], "processed_at": now_datetime(),
    })
    frappe.db.commit()
    frappe.log_error(title=f"K95 NIMR intake failed: {external_pr_id or 'unknown'}", message=frappe.get_traceback())
    frappe.throw(clear_text, frappe.ValidationError)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def receive_purchase_request(payload=None, **kwargs):
    settings = get_settings()
    data, raw = _payload_and_raw(payload, **kwargs)
    _authenticate(settings, raw)
    raw_request = data.get("purchase_request") or data.get("data") or data
    external_pr_hint = raw_request.get("external_pr_id") or raw_request.get("pr_id") or raw_request.get("id")
    event_id = data.get("event_id") or raw_request.get("event_id") or f"evt_{uuid.uuid4().hex}"
    idempotency_key = data.get("idempotency_key") or frappe.get_request_header("X-Idempotency-Key") or event_id
    prior = frappe.db.get_value("K95 Inbound Event", {"idempotency_key": idempotency_key}, ["name", "nimr", "status", "attempt_count"], as_dict=True)
    if prior and prior.nimr:
        return _response(prior.nimr, duplicate=True)
    if prior:
        event = frappe.get_doc("K95 Inbound Event", prior.name)
        event.db_set({
            "status": "PROCESSING", "attempt_count": (prior.attempt_count or 0) + 1,
            "payload": raw, "payload_hash": hashlib.sha256(raw.encode()).hexdigest(), "last_error": None,
        })
        event.reload()
    else:
        event = frappe.get_doc({
            "doctype": "K95 Inbound Event", "event_id": event_id, "idempotency_key": idempotency_key,
            "event_type": data.get("event_type") or "purchase_request.store_verified",
            "event_version": str(data.get("event_version") or 1), "correlation_id": data.get("correlation_id"),
            "external_pr_id": external_pr_hint, "payload": raw,
            "payload_hash": hashlib.sha256(raw.encode()).hexdigest(), "status": "PROCESSING",
            "attempt_count": 1, "received_at": now_datetime(),
        }).insert(ignore_permissions=True)
    # Preserve receipt/failure diagnostics even if the NIMR transaction fails.
    frappe.db.commit()
    try:
        request, lines, external_pr_id = _normalize(data)
    except Exception as exc:
        raw_lines = raw_request.get("lines") or raw_request.get("items") or []
        line_ids = [line.get("external_line_id") or line.get("line_id") or "?" for line in raw_lines]
        _fail_inbound_event(event, external_pr_hint, line_ids, exc)
    existing_nimr = frappe.db.get_value("New Item Material Request", {"external_pr_id": external_pr_id}, "name")
    if existing_nimr:
        event.db_set({"nimr": existing_nimr, "status": "PROCESSED", "processed_at": now_datetime()})
        return _response(existing_nimr, duplicate=True)
    savepoint = f"nimr_intake_{uuid.uuid4().hex}"
    frappe.db.savepoint(savepoint)
    try:
        doc = _build_nimr_document(settings, data, request, lines, external_pr_id, event)
        doc.insert(ignore_permissions=True)
        doc.db_set({"integration_status": "Processed", "last_processed_at": now_datetime()})
        event.db_set({"nimr": doc.name, "status": "PROCESSED", "processed_at": now_datetime()})
        return _response(doc.name)
    except Exception as exc:
        frappe.db.rollback(save_point=savepoint)
        _fail_inbound_event(event, external_pr_id, [line.get("external_line_id") or "?" for line in lines], exc)
