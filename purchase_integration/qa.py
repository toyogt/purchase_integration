import uuid

import frappe

from purchase_integration.api import _build_nimr_document, _normalize
from purchase_integration.events import publish_item, publish_material_request, publish_nimr, publish_purchase_order
from purchase_integration.integration import canonical_json, deliver_event, is_idempotent_success, queue_event, sign


def dry_test():
    checks = {}
    checks["doctypes"] = all(frappe.db.exists("DocType", dt) for dt in ("K95 Inbound Event", "K95 Outbound Event", "Purchase Integration Settings"))
    required_fields = {
        "Item": "custom_k95_item_id",
        "Material Request Item": "custom_k95_line_id", "Purchase Order Item": "custom_k95_line_id",
        "NIMR Item": "k95_item_id",
    }
    checks["identity_fields"] = all(frappe.get_meta(dt).has_field(field) for dt, field in required_fields.items())
    request, lines, pr_id = _normalize({
        "external_pr_id": "K95-DRY-PR-1", "items": [
            {"line_id": "L1", "item_name": "Allowed", "quantity": 2, "store_decision": "Purchase Required", "send_to_erpnext": True},
            {"line_id": "L2", "item_name": "Stock", "quantity": 1, "store_decision": "Fulfilled from Stock", "send_to_erpnext": True},
            {"line_id": "L3", "item_name": "Not ready", "quantity": 1, "send_to_erpnext": False},
        ],
    })
    checks["purchase_required_filter"] = pr_id == "K95-DRY-PR-1" and len(lines) == 1 and lines[0]["external_line_id"] == "L1"
    body = canonical_json({"b": 2, "a": 1})
    checks["canonical_hmac"] = body == '{"a":1,"b":2}' and sign("secret", "POST", "/path", "1", body) == sign("secret", "POST", "/path", "1", body)
    response = type("Response", (), {"status_code": 409, "text": "Already processed"})()
    checks["idempotent_409"] = is_idempotent_success(response)
    missing_result = deliver_event(f"missing_{uuid.uuid4().hex}")
    checks["missing_outbound_event_guard"] = bool(missing_result and missing_result.get("reason") == "event_not_found")

    intake_savepoint = f"pi_intake_{uuid.uuid4().hex}"
    frappe.db.savepoint(intake_savepoint)
    settings = frappe.get_single("Purchase Integration Settings")
    test_id = uuid.uuid4().hex
    existing_item_name = frappe.db.get_value("Item", {}, "item_name") or "Name-only match test"
    intake_data = {
        "event_id": f"evt_{test_id}", "idempotency_key": f"idem_{test_id}",
        "event_version": 1, "correlation_id": f"corr_{test_id}",
        "purchase_request": {
            "external_pr_id": f"K95-DRY-{test_id}", "request_date": "2026-08-22T09:26:06.489Z",
            "submitted_at": "2026-08-22T09:27:06.489Z", "title": "Live failure regression",
            "items": [{
                "line_id": f"{test_id}-L001", "item_name": existing_item_name,
                "requested_purchase_quantity": 2, "quantity": 2, "uom": "piece",
                "required_by": "2026-08-29T00:00:00.000Z", "store_decision": "Purchase Required",
                "send_to_erpnext": True,
            }],
            "attachments": [{"id": f"att_{test_id}", "line_id": f"{test_id}-L001", "media_type": "image", "file_name": "test.jpg"}],
        },
    }
    request, intake_lines, intake_pr_id = _normalize(intake_data)
    inbound = frappe.get_doc({
        "doctype": "K95 Inbound Event", "event_id": intake_data["event_id"],
        "idempotency_key": intake_data["idempotency_key"], "event_type": "purchase_request.store_verified",
        "external_pr_id": intake_pr_id, "payload": canonical_json(intake_data), "payload_hash": test_id,
        "status": "PROCESSING", "attempt_count": 1,
    }).insert(ignore_permissions=True)
    intake_doc = _build_nimr_document(settings, intake_data, request, intake_lines, intake_pr_id, inbound)
    intake_doc.insert(ignore_permissions=True)
    checks["iso_datetime_intake"] = bool(intake_doc.request_date and intake_doc.submitted_at)
    checks["free_text_new_item_uom"] = intake_doc.items[0].requested_uom == "piece" and not intake_doc.items[0].purchase_uom
    checks["lowercase_attachment_media"] = intake_doc.attachments[0].media_type == "IMAGE"
    checks["name_only_item_not_matched"] = not intake_doc.items[0].erpnext_item
    try:
        _normalize({
            "external_pr_id": f"K95-ZERO-{test_id}",
            "items": [{"line_id": "ZERO-L1", "item_name": "Zero", "requested_purchase_quantity": 0,
                       "quantity": 10, "store_decision": "Purchase Required", "send_to_erpnext": True}],
        })
        checks["zero_qty_rejected"] = False
    except frappe.ValidationError as exc:
        checks["zero_qty_rejected"] = "greater than 0" in str(exc)
    checks["zero_qty_created_no_nimr"] = not frappe.db.exists("New Item Material Request", f"K95-ZERO-{test_id}")
    frappe.db.rollback(save_point=intake_savepoint)

    savepoint = f"pi_dry_{uuid.uuid4().hex}"
    frappe.db.savepoint(savepoint)
    frappe.db.set_single_value("Purchase Integration Settings", "integration_enabled", 0)
    event_name = queue_event(
        "dry_test.event", "Dry Test", uuid.uuid4().hex,
        {"event_version": 1, "modified_at": uuid.uuid4().hex}, "item",
    )
    checks["outbox_records_while_disabled"] = bool(event_name and frappe.db.exists("K95 Outbound Event", event_name))
    frappe.db.rollback(save_point=savepoint)
    publisher_savepoint = f"pi_publishers_{uuid.uuid4().hex}"
    frappe.db.savepoint(publisher_savepoint)
    frappe.db.set_single_value("Purchase Integration Settings", "integration_enabled", 0)
    item_name = frappe.db.get_value("Item", {}, "name")
    item = frappe.get_doc("Item", item_name)
    publish_item(item)
    checks["item_hook"] = True
    mr_name = frappe.db.get_value("Material Request", {}, "name")
    if mr_name:
        publish_material_request(frappe.get_doc("Material Request", mr_name))
    checks["material_request_hook"] = True
    po_name = frappe.db.get_value("Purchase Order", {}, "name")
    if po_name:
        publish_purchase_order(frappe.get_doc("Purchase Order", po_name))
    checks["purchase_order_hook"] = True
    nimr_name = frappe.db.get_value("New Item Material Request", {}, "name")
    if nimr_name:
        publish_nimr(frappe.get_doc("New Item Material Request", nimr_name))
    checks["nimr_status_hook"] = True
    frappe.db.rollback(save_point=publisher_savepoint)
    checks["event_schema"] = all(frappe.get_meta("K95 Outbound Event").has_field(field) for field in ("idempotency_key", "payload_hash", "next_retry_at", "attempt_count"))
    checks["hooks_loaded"] = bool(frappe.get_hooks("scheduler_events"))
    return {"passed": all(checks.values()), "checks": checks}
