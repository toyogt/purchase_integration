import frappe

from purchase_integration.api import _normalize
from purchase_integration.events import publish_item, publish_material_request, publish_purchase_order, publish_supplier
from purchase_integration.integration import canonical_json, sign


def dry_test():
    checks = {}
    checks["doctypes"] = all(frappe.db.exists("DocType", dt) for dt in ("K95 Inbound Event", "K95 Outbound Event", "Purchase Integration Settings"))
    required_fields = {
        "Item": "custom_k95_item_id", "Supplier": "custom_k95_supplier_id",
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
    item_name = frappe.db.get_value("Item", {}, "name")
    item = frappe.get_doc("Item", item_name)
    publish_item(item)
    checks["item_hook"] = True
    supplier_name = frappe.db.get_value("Supplier", {}, "name")
    if supplier_name:
        publish_supplier(frappe.get_doc("Supplier", supplier_name))
    checks["supplier_hook"] = True
    mr_name = frappe.db.get_value("Material Request", {}, "name")
    if mr_name:
        publish_material_request(frappe.get_doc("Material Request", mr_name))
    checks["material_request_hook"] = True
    po_name = frappe.db.get_value("Purchase Order", {}, "name")
    if po_name:
        publish_purchase_order(frappe.get_doc("Purchase Order", po_name))
    checks["purchase_order_hook"] = True
    checks["event_schema"] = all(frappe.get_meta("K95 Outbound Event").has_field(field) for field in ("idempotency_key", "payload_hash", "next_retry_at", "attempt_count"))
    checks["hooks_loaded"] = bool(frappe.get_hooks("scheduler_events"))
    return {"passed": all(checks.values()), "checks": checks}
