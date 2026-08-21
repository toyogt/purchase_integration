import hashlib
import hmac
import json
import time
import uuid
from urllib.parse import urljoin

import frappe
import requests
from frappe import _
from frappe.utils import add_to_date, now_datetime


ENDPOINT_FIELDS = {
    "item": "item_upsert_path",
    "supplier": "supplier_upsert_path",
    "material_request": "material_request_upsert_path",
    "purchase_order": "purchase_order_upsert_path",
    "purchase_request_status": "purchase_request_status_path",
    "master_data": "master_data_upsert_path",
    "attachment": "attachment_upsert_path",
}


def get_settings():
    return frappe.get_single("Purchase Integration Settings")


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sign(secret, method, path, timestamp, raw_body):
    message = "\n".join((method.upper(), path, str(timestamp), raw_body))
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def outbound_headers(settings, path, body, event):
    headers = {
        "Content-Type": "application/json",
        "X-K95-Event-ID": event.event_id,
        "X-Idempotency-Key": event.idempotency_key,
    }
    if settings.outbound_auth_type == "Bearer Token":
        token = settings.get_password("outbound_bearer_token")
        if not token:
            frappe.throw(_("K95 Bearer Token is not configured."))
        headers["Authorization"] = f"Bearer {token}"
    else:
        secret = settings.get_password("outbound_hmac_secret")
        if not settings.outbound_key_id or not secret:
            frappe.throw(_("K95 outbound HMAC Key ID and Secret are required."))
        timestamp = str(int(time.time()))
        headers.update({
            "X-K95-Key": settings.outbound_key_id,
            "X-K95-Timestamp": timestamp,
            "X-K95-Signature": sign(secret, "POST", path, timestamp, body),
        })
    return headers


def queue_event(event_type, aggregate_type, aggregate_id, payload, endpoint_key, *, external_pr_id=None, external_line_id=None, correlation_id=None):
    settings = get_settings()
    path = settings.get(ENDPOINT_FIELDS[endpoint_key])
    if not path:
        frappe.throw(_("No endpoint is configured for {0}.").format(endpoint_key))
    body = canonical_json(payload)
    version = int(payload.get("event_version") or 1)
    idempotency_key = f"{event_type}:{aggregate_id}:{payload.get('modified_at') or version}"
    existing = frappe.db.get_value("K95 Outbound Event", {"idempotency_key": idempotency_key}, "name")
    if existing:
        return existing
    event = frappe.get_doc({
        "doctype": "K95 Outbound Event",
        "event_id": f"evt_{uuid.uuid4().hex}",
        "event_type": event_type,
        "event_version": version,
        "idempotency_key": idempotency_key,
        "correlation_id": correlation_id,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "external_pr_id": external_pr_id,
        "external_line_id": external_line_id,
        "endpoint_path": path,
        "payload": body,
        "payload_hash": hashlib.sha256(body.encode()).hexdigest(),
        "status": "PENDING",
        "next_retry_at": now_datetime(),
    }).insert(ignore_permissions=True)
    # Disabling integration pauses transport only. The durable business event is
    # still recorded so no Item, Supplier, NIMR, MR, or PO update is lost.
    if settings.integration_enabled:
        frappe.enqueue("purchase_integration.integration.deliver_event", event_name=event.name, queue="short", enqueue_after_commit=True)
    return event.name


def is_idempotent_success(response):
    return response.status_code == 409 and "already processed" in (response.text or "").lower()


def deliver_event(event_name):
    event = frappe.get_doc("K95 Outbound Event", event_name)
    if event.status in ("DELIVERED", "CANCELLED", "DEAD_LETTER"):
        return
    settings = get_settings()
    if not settings.integration_enabled:
        return
    event.db_set({"status": "PROCESSING", "last_attempt_at": now_datetime(), "attempt_count": (event.attempt_count or 0) + 1})
    body = event.payload
    url = urljoin(settings.k95_base_url.rstrip("/") + "/", event.endpoint_path.lstrip("/"))
    try:
        response = requests.post(
            url,
            data=body.encode(),
            headers=outbound_headers(settings, event.endpoint_path, body, event),
            timeout=int(settings.request_timeout_seconds or 30),
            verify=bool(settings.verify_ssl),
        )
        event.db_set({"response_status_code": response.status_code, "response_body": response.text[:10000]})
        if not is_idempotent_success(response):
            response.raise_for_status()
        event.db_set({"status": "DELIVERED", "delivered_at": now_datetime(), "last_error": None})
        frappe.db.set_single_value("Purchase Integration Settings", "last_successful_sync_at", now_datetime())
    except Exception as exc:
        attempts = int(event.attempt_count or 1)
        maximum = int(settings.max_retry_attempts or 10)
        if attempts >= maximum:
            status = "DEAD_LETTER"
            next_retry = None
        else:
            status = "RETRY"
            delay = min(
                int(settings.initial_retry_delay_seconds or 60) * float(settings.retry_backoff_multiplier or 2) ** max(attempts - 1, 0),
                int(settings.maximum_retry_delay_seconds or 3600),
            )
            next_retry = add_to_date(now_datetime(), seconds=int(delay))
        event.db_set({"status": status, "next_retry_at": next_retry, "last_error": str(exc)[:10000]})
        frappe.log_error(title=f"K95 delivery failed: {event.event_id}", message=frappe.get_traceback())


def process_due_events(limit=50):
    names = frappe.get_all(
        "K95 Outbound Event",
        filters={"status": ["in", ["PENDING", "RETRY"]], "next_retry_at": ["<=", now_datetime()]},
        pluck="name",
        order_by="creation asc",
        limit_page_length=limit,
    )
    for name in names:
        frappe.enqueue("purchase_integration.integration.deliver_event", event_name=name, queue="short")


@frappe.whitelist()
def retry_event(event_name):
    frappe.has_permission("K95 Outbound Event", ptype="write", throw=True)
    frappe.db.set_value("K95 Outbound Event", event_name, {"status": "PENDING", "next_retry_at": now_datetime(), "last_error": None})
    frappe.enqueue("purchase_integration.integration.deliver_event", event_name=event_name, queue="short", enqueue_after_commit=True)
    return {"queued": True, "event": event_name}


@frappe.whitelist()
def test_connection():
    settings = get_settings()
    frappe.has_permission("Purchase Integration Settings", ptype="write", throw=True)
    try:
        response = requests.get(settings.k95_base_url, timeout=int(settings.request_timeout_seconds or 30), verify=bool(settings.verify_ssl))
        response.raise_for_status()
        values = {"last_connection_status": "Successful", "last_connection_at": now_datetime(), "last_connection_error": None}
        result = {"success": True, "status_code": response.status_code}
    except Exception as exc:
        values = {"last_connection_status": "Failed", "last_connection_at": now_datetime(), "last_connection_error": str(exc)}
        result = {"success": False, "error": str(exc)}
    for fieldname, value in values.items():
        frappe.db.set_single_value("Purchase Integration Settings", fieldname, value)
    return result
