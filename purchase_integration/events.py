import frappe

from purchase_integration.integration import queue_event


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


def publish_nimr(doc, method=None):
    payload = {
        "event_version": 1,
        "modified_at": str(doc.modified),
        "external_pr_id": doc.external_pr_id,
        "correlation_id": doc.correlation_id,
        "nimr_id": doc.name,
        "status": doc.processing_status,
        "docstatus": doc.docstatus,
        "total_lines": doc.total_lines,
        "ready_for_mr_lines": doc.ready_for_mr_lines,
        "pending_item_verification_lines": doc.pending_item_verification_lines,
        "mr_created_lines": doc.mr_created_lines,
        "ordered_lines": doc.ordered_lines,
        "failed_lines": doc.failed_lines,
        "lines": [{
            "external_line_id": row.external_line_id,
            "k95_item_id": row.k95_item_id,
            "erpnext_item_code": row.erpnext_item,
            "item_resolution_status": row.item_resolution_status,
            "processing_status": row.processing_status,
            "requested_quantity": row.requested_qty,
            "final_purchase_quantity": row.final_purchase_qty,
            "mr_created_quantity": row.mr_created_qty,
            "ordered_quantity": row.ordered_qty,
        } for row in doc.items],
    }
    queue_event(
        "purchase_request.status_changed", "New Item Material Request", doc.name,
        payload, "purchase_request_status", external_pr_id=doc.external_pr_id,
        correlation_id=doc.correlation_id,
    )


def _transaction_payload(doc, rows=None):
    lines = []
    for row in rows if rows is not None else doc.items:
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
    linked_rows = [row for row in doc.items if row.custom_k95_pr_id and row.custom_nimr]
    if not linked_rows:
        return
    pr_id = linked_rows[0].custom_k95_pr_id
    payload = {
        "event_version": 1, "modified_at": str(doc.modified), "material_request": doc.name,
        "status": doc.status, "docstatus": doc.docstatus, "transaction_date": str(doc.transaction_date or ""),
        "schedule_date": str(doc.schedule_date or ""), "company": doc.company,
        "lines": _transaction_payload(doc, linked_rows),
    }
    queue_event("material_request.upsert", "Material Request", doc.name, payload, "material_request", external_pr_id=pr_id)


def publish_purchase_order(doc, method=None):
    linked_rows = [row for row in doc.items if row.custom_k95_pr_id and row.custom_nimr]
    if not linked_rows:
        return
    pr_id = linked_rows[0].custom_k95_pr_id
    payload = {
        "event_version": 1, "modified_at": str(doc.modified), "purchase_order": doc.name,
        "status": doc.status, "docstatus": doc.docstatus, "supplier": doc.supplier,
        "supplier_name": doc.supplier_name, "transaction_date": str(doc.transaction_date or ""),
        "schedule_date": str(doc.schedule_date or ""), "currency": doc.currency,
        "net_total": doc.net_total, "grand_total": doc.grand_total, "company": doc.company,
        "per_received": doc.per_received, "per_billed": doc.per_billed,
        "lines": _transaction_payload(doc, linked_rows),
    }
    queue_event("purchase_order.upsert", "Purchase Order", doc.name, payload, "purchase_order", external_pr_id=pr_id)
