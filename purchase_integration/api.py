import hashlib
import hmac
import ipaddress
import json
import time
import uuid

import frappe
from frappe import _
from frappe.utils import now_datetime

from purchase_integration.integration import canonical_json, get_settings, sign


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
        eligible.append(line)
    if not eligible:
        frappe.throw(_("No Purchase Required lines were supplied."))
    return request, eligible, external_pr_id


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


@frappe.whitelist(allow_guest=True, methods=["POST"])
def receive_purchase_request(payload=None, **kwargs):
    settings = get_settings()
    data, raw = _payload_and_raw(payload, **kwargs)
    _authenticate(settings, raw)
    request, lines, external_pr_id = _normalize(data)
    event_id = data.get("event_id") or request.get("event_id") or f"evt_{uuid.uuid4().hex}"
    idempotency_key = data.get("idempotency_key") or frappe.get_request_header("X-Idempotency-Key") or event_id
    prior = frappe.db.get_value("K95 Inbound Event", {"idempotency_key": idempotency_key}, ["nimr", "status"], as_dict=True)
    if prior and prior.nimr:
        return _response(prior.nimr, duplicate=True)
    existing_nimr = frappe.db.get_value("New Item Material Request", {"external_pr_id": external_pr_id}, "name")
    event = frappe.get_doc({
        "doctype": "K95 Inbound Event", "event_id": event_id, "idempotency_key": idempotency_key,
        "event_type": data.get("event_type") or "purchase_request.store_verified",
        "event_version": str(data.get("event_version") or 1), "correlation_id": data.get("correlation_id"),
        "external_pr_id": external_pr_id, "payload": raw,
        "payload_hash": hashlib.sha256(raw.encode()).hexdigest(), "status": "PROCESSING",
        "attempt_count": 1, "received_at": now_datetime(),
    }).insert(ignore_permissions=True)
    if existing_nimr:
        event.db_set({"nimr": existing_nimr, "status": "PROCESSED", "processed_at": now_datetime()})
        return _response(existing_nimr, duplicate=True)
    requester = request.get("requester") or {}
    doc = frappe.get_doc({
        "doctype": "New Item Material Request", "external_pr_id": external_pr_id,
        "external_document_id": request.get("document_id"), "correlation_id": data.get("correlation_id"),
        "source_event_id": event_id, "source_event_version": str(data.get("event_version") or 1),
        "source_record_version": request.get("record_version") or 1, "idempotency_key": idempotency_key,
        "company": request.get("company") or settings.company, "request_title": request.get("title") or request.get("pr_number"),
        "priority": request.get("priority") or "Medium", "request_date": request.get("request_date"),
        "submitted_at": request.get("submitted_at"), "requester_user_id": requester.get("user_id"),
        "requester_employee_id": requester.get("employee_id"), "requester_name": requester.get("name"),
        "requester_email": requester.get("email"), "department_name": request.get("department"),
        "requested_on_behalf_of": request.get("requested_on_behalf_of"), "received_at": now_datetime(),
        "integration_status": "Processing", "source_payload_hash": event.payload_hash, "inbound_event": event.name,
    })
    for index, line in enumerate(lines, 1):
        qty = line.get("requested_purchase_quantity") or line.get("purchase_required_qty") or line.get("quantity")
        doc.append("items", {
            "external_line_id": line["external_line_id"], "line_number": line.get("line_number") or index,
            "item_source": line.get("item_source") or "NEW", "external_item_code": line.get("k95_item_code") or line.get("item_code"),
            "k95_item_id": line.get("k95_item_id"), "requested_item_name": line.get("item_name") or line.get("name"),
            "requested_description": line.get("description"), "requirement": line.get("requirement"),
            "need_purpose": line.get("need_purpose"), "requested_qty": line.get("quantity") or qty,
            "purchase_required_qty": qty, "final_purchase_qty": qty,
            "requested_uom": line.get("uom"), "purchase_uom": line.get("uom"),
            "requested_required_by": line.get("required_by"), "schedule_date": line.get("required_by"),
            "purchase_description": line.get("description"), "purchase_remarks": line.get("remarks"),
            "primary_image": line.get("primary_image_url"),
        })
    for attachment in request.get("attachments") or []:
        doc.append("attachments", {
            "external_attachment_id": attachment.get("attachment_id") or attachment.get("id"),
            "external_line_id": attachment.get("line_id"), "media_type": attachment.get("media_type") or "DOCUMENT",
            "file_name": attachment.get("file_name"), "mime_type": attachment.get("mime_type"),
            "file_size": attachment.get("file_size"), "file_hash": attachment.get("sha256"),
            "external_file_url": attachment.get("url"), "caption": attachment.get("caption"),
            "is_primary_image": attachment.get("is_primary_image") or 0,
        })
    doc.insert(ignore_permissions=True)
    doc.db_set({"integration_status": "Processed", "last_processed_at": now_datetime()})
    event.db_set({"nimr": doc.name, "status": "PROCESSED", "processed_at": now_datetime()})
    return _response(doc.name)
