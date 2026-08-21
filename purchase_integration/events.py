import re

import frappe
from frappe import _

from purchase_integration.integration import queue_event


def _clean(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def validate_supplier(doc, method=None):
    """Keep unapproved K95 suppliers on hold and block exact GSTIN/postal duplicates."""
    if doc.custom_k95_approval_status != "Approved":
        doc.disabled = 1
    elif doc.custom_k95_approval_status == "Approved":
        doc.disabled = 0
    gstin, postal = _clean(doc.tax_id), _clean(doc.custom_k95_postal_code)
    if not gstin or not postal:
        return
    candidates = frappe.get_all("Supplier", filters={"tax_id": doc.tax_id, "name": ["!=", doc.name or ""]}, fields=["name", "custom_k95_postal_code"])
    for candidate in candidates:
        if _clean(candidate.custom_k95_postal_code) == postal:
            frappe.throw(_("Supplier {0} already has the same GSTIN and postal code. Map it to K95 instead.").format(candidate.name))


def propagate_po_traceability(doc, method=None):
    for row in doc.items:
        if not row.material_request_item:
            continue
        values = frappe.db.get_value(
            "Material Request Item", row.material_request_item,
            ["custom_k95_pr_id", "custom_k95_line_id", "custom_k95_item_id", "custom_nimr", "custom_nimr_item_row"], as_dict=True,
        )
        if values:
            for fieldname, value in values.items():
                row.set(fieldname, value)


def _item_payload(doc):
    return {
        "event_version": 1, "modified_at": str(doc.modified), "erpnext_item_code": doc.name,
        "k95_item_id": doc.custom_k95_item_id, "k95_item_code": doc.custom_k95_item_code,
        "item_name": doc.item_name, "description": doc.description, "item_group": doc.item_group,
        "stock_uom": doc.stock_uom, "hsn_sac": doc.gst_hsn_code, "disabled": bool(doc.disabled),
        "is_stock_item": bool(doc.is_stock_item), "image": doc.image,
    }


def publish_item(doc, method=None):
    if not (doc.get("custom_publish_to_k95") or doc.custom_k95_item_id):
        return
    queue_event("item.upsert", "Item", doc.name, _item_payload(doc), "item")


def publish_supplier(doc, method=None):
    if not doc.custom_publish_to_k95:
        return
    payload = {
        "event_version": 1, "modified_at": str(doc.modified), "erpnext_supplier_id": doc.name,
        "k95_supplier_id": doc.custom_k95_supplier_id, "supplier_name": doc.supplier_name,
        "supplier_group": doc.supplier_group, "supplier_type": doc.supplier_type, "gstin": doc.tax_id,
        "postal_code": doc.custom_k95_postal_code, "approval_status": doc.custom_k95_approval_status,
        "disabled": bool(doc.disabled), "country": doc.country,
    }
    queue_event("supplier.upsert", "Supplier", doc.name, payload, "supplier")


def _transaction_payload(doc):
    lines = []
    for row in doc.items:
        lines.append({
            "erpnext_line_id": row.name, "k95_pr_id": row.custom_k95_pr_id,
            "k95_line_id": row.custom_k95_line_id, "k95_item_id": row.custom_k95_item_id,
            "item_code": row.item_code, "item_name": row.item_name, "description": row.description,
            "qty": row.qty, "uom": row.uom, "schedule_date": str(row.schedule_date or ""),
            "warehouse": row.warehouse, "nimr": row.custom_nimr, "nimr_item_row": row.custom_nimr_item_row,
            "material_request": row.get("material_request"), "material_request_item": row.get("material_request_item"),
            "rate": row.get("rate"), "amount": row.get("amount"),
        })
    return lines


def publish_material_request(doc, method=None):
    payload = {
        "event_version": 1, "modified_at": str(doc.modified), "material_request": doc.name,
        "status": doc.status, "docstatus": doc.docstatus, "transaction_date": str(doc.transaction_date or ""),
        "schedule_date": str(doc.schedule_date or ""), "company": doc.company, "lines": _transaction_payload(doc),
    }
    pr_id = next((row.custom_k95_pr_id for row in doc.items if row.custom_k95_pr_id), None)
    queue_event("material_request.upsert", "Material Request", doc.name, payload, "material_request", external_pr_id=pr_id)


def publish_purchase_order(doc, method=None):
    payload = {
        "event_version": 1, "modified_at": str(doc.modified), "purchase_order": doc.name,
        "status": doc.status, "docstatus": doc.docstatus, "supplier": doc.supplier,
        "supplier_name": doc.supplier_name, "transaction_date": str(doc.transaction_date or ""),
        "schedule_date": str(doc.schedule_date or ""), "currency": doc.currency,
        "net_total": doc.net_total, "grand_total": doc.grand_total, "company": doc.company,
        "per_received": doc.per_received, "per_billed": doc.per_billed, "lines": _transaction_payload(doc),
    }
    pr_id = next((row.custom_k95_pr_id for row in doc.items if row.custom_k95_pr_id), None)
    queue_event("purchase_order.upsert", "Purchase Order", doc.name, payload, "purchase_order", external_pr_id=pr_id)
