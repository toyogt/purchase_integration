import hashlib
import json

import frappe
from frappe.utils import now_datetime
from frappe.utils.file_manager import save_file


SAMPLE_PR_ID = "K95-TEST-PR-0003"
SAMPLE_EVENT_ID = "evt_K95-TEST-PR-0003_erp_release_v1"


def _first_existing(doctype, preferred=None, filters=None):
    if preferred and frappe.db.exists(doctype, preferred):
        return preferred
    return frappe.db.get_value(doctype, filters or {}, "name")


def run():
    existing = frappe.db.get_value(
        "New Item Material Request", {"external_pr_id": SAMPLE_PR_ID}, "name"
    )
    if existing:
        return {"created": False, "nimr": existing, "reason": "sample already exists"}

    company = _first_existing("Company", "K95 Foods Private Limited")
    item_code = _first_existing("Item", "ITEM-00032", {"disabled": 0})
    item = frappe.get_doc("Item", item_code)
    uom = item.stock_uom or _first_existing("UOM", "Nos")
    warehouse = frappe.db.get_value(
        "Warehouse", {"company": company, "is_group": 0, "disabled": 0}, "name"
    )

    payload = {
        "event_id": SAMPLE_EVENT_ID,
        "event_type": "purchase_request.ready_for_erpnext",
        "event_version": "1.0",
        "idempotency_key": f"{SAMPLE_PR_ID}:ERP_RELEASE:1",
        "correlation_id": f"corr_{SAMPLE_PR_ID}",
        "purchase_request": {
            "pr_number": SAMPLE_PR_ID,
            "company": company,
            "requester_name": "K95 Sample Requester",
            "requester_employee_id": "EMP-SAMPLE-001",
            "requester_email": "sample.requester@k95.local",
            "department": "Production",
            "priority": "Medium",
            "store_verified_by": "Sample Store Manager",
        },
        "items": [
            {
                "line_id": f"{SAMPLE_PR_ID}-L001",
                "item_source": "MASTER",
                "item_code": item_code,
                "item_name": item.item_name,
                "description": "Existing ERPNext Item used for NIMR integration testing.",
                "requirement": "Production trial requirement",
                "need_purpose": "Required to test the K95 to ERPNext purchase workflow.",
                "requested_qty": 12,
                "hod_approved_qty": 10,
                "purchase_required_qty": 8,
                "uom": uom,
                "required_by": "2026-08-31",
            },
            {
                "line_id": f"{SAMPLE_PR_ID}-L002",
                "item_source": "NEW",
                "item_code": None,
                "item_name": "Sample Stainless-Steel Measuring Cup",
                "description": "Food-grade stainless-steel measuring cup with long handle.",
                "requirement": "Quality sampling",
                "need_purpose": "Required for safe collection of production samples.",
                "requested_qty": 4,
                "hod_approved_qty": 4,
                "purchase_required_qty": 4,
                "uom": uom,
                "required_by": "2026-09-02",
            },
        ],
    }
    payload_text = json.dumps(payload, indent=2, sort_keys=True)
    payload_hash = hashlib.sha256(payload_text.encode()).hexdigest()

    inbound = frappe.get_doc(
        {
            "doctype": "K95 Inbound Event",
            "event_id": SAMPLE_EVENT_ID,
            "idempotency_key": f"{SAMPLE_PR_ID}:ERP_RELEASE:1",
            "event_type": "purchase_request.ready_for_erpnext",
            "event_version": "1.0",
            "correlation_id": f"corr_{SAMPLE_PR_ID}",
            "external_pr_id": SAMPLE_PR_ID,
            "payload": payload_text,
            "payload_hash": payload_hash,
            "status": "PROCESSING",
            "attempt_count": 1,
            "received_at": now_datetime(),
        }
    ).insert(ignore_permissions=True)

    nimr = frappe.get_doc(
        {
            "doctype": "New Item Material Request",
            "pr_unique_id": SAMPLE_PR_ID,
            "external_pr_id": SAMPLE_PR_ID,
            "external_document_id": "k95_sample_document_001",
            "correlation_id": f"corr_{SAMPLE_PR_ID}",
            "source_event_id": SAMPLE_EVENT_ID,
            "source_event_version": "1.0",
            "source_record_version": 1,
            "idempotency_key": f"{SAMPLE_PR_ID}:ERP_RELEASE:1",
            "source_system": "K95_ERP",
            "company": company,
            "request_title": "Sample mixed-item Purchase Request",
            "priority": "Medium",
            "request_date": now_datetime(),
            "submitted_at": now_datetime(),
            "requester_user_id": "USR-SAMPLE-001",
            "requester_employee_id": "EMP-SAMPLE-001",
            "requester_name": "K95 Sample Requester",
            "requester_email": "sample.requester@k95.local",
            "department_name": "Production",
            "hod_status": "Approved",
            "hod_approved_by": "Sample HOD",
            "hod_approved_by_email": "sample.hod@k95.local",
            "hod_approved_at": now_datetime(),
            "hod_remarks": "Approved for integration testing.",
            "store_status": "Verified",
            "store_verified_by": "Sample Store Manager",
            "store_verified_by_email": "sample.store@k95.local",
            "store_verified_at": now_datetime(),
            "store_remarks": "Purchase quantities verified for sample data.",
            "status": "Draft",
            "processing_status": "Pending Item Verification",
            "total_lines": 2,
            "ready_for_mr_lines": 1,
            "pending_item_verification_lines": 1,
            "mr_created_lines": 0,
            "ordered_lines": 0,
            "failed_lines": 0,
            "integration_status": "Processed",
            "received_at": now_datetime(),
            "last_processed_at": now_datetime(),
            "source_payload_hash": payload_hash,
            "inbound_event": inbound.name,
            "items": [
                {
                    "external_line_id": f"{SAMPLE_PR_ID}-L001",
                    "line_number": 1,
                    "item_source": "MASTER",
                    "external_item_code": item_code,
                    "requested_item_name": item.item_name,
                    "requested_description": "Existing ERPNext Item used for NIMR integration testing.",
                    "requirement": "Production trial requirement",
                    "need_purpose": "Required to test the K95 to ERPNext purchase workflow.",
                    "requested_qty": 12,
                    "hod_approved_qty": 10,
                    "store_verified_qty": 10,
                    "purchase_required_qty": 8,
                    "requested_uom": uom,
                    "requested_required_by": "2026-08-30",
                    "hod_required_by": "2026-08-31",
                    "store_required_by": "2026-08-31",
                    "current_stock_qty": 1,
                    "already_on_order_qty": 1,
                    "calculated_shortage_qty": 8,
                    "stock_snapshot_at": now_datetime(),
                    "store_line_remarks": "Existing stock and open orders checked.",
                    "erpnext_item": item_code,
                    "item_resolution_status": "AUTO_MATCHED",
                    "resolution_method": "EXACT_ITEM_CODE",
                    "final_purchase_qty": 8,
                    "purchase_uom": uom,
                    "conversion_factor": 1,
                    "schedule_date": "2026-08-31",
                    "target_warehouse": warehouse,
                    "purchase_description": "Existing ERPNext Item used for NIMR integration testing.",
                    "publish_item_to_k95": 0,
                    "pending_mr_qty": 8,
                    "processing_status": "READY_FOR_MR",
                },
                {
                    "external_line_id": f"{SAMPLE_PR_ID}-L002",
                    "line_number": 2,
                    "item_source": "NEW",
                    "requested_item_name": "Sample Stainless-Steel Measuring Cup",
                    "requested_description": "Food-grade stainless-steel measuring cup with long handle.",
                    "requirement": "Quality sampling",
                    "need_purpose": "Required for safe collection of production samples.",
                    "requested_qty": 4,
                    "hod_approved_qty": 4,
                    "store_verified_qty": 4,
                    "purchase_required_qty": 4,
                    "requested_uom": uom,
                    "requested_required_by": "2026-09-02",
                    "hod_required_by": "2026-09-02",
                    "store_required_by": "2026-09-02",
                    "current_stock_qty": 0,
                    "already_on_order_qty": 0,
                    "calculated_shortage_qty": 4,
                    "stock_snapshot_at": now_datetime(),
                    "store_line_remarks": "No matching ERPNext Item found.",
                    "item_resolution_status": "PENDING_ITEM_CREATION",
                    "final_purchase_qty": 4,
                    "purchase_uom": uom,
                    "conversion_factor": 1,
                    "schedule_date": "2026-09-02",
                    "target_warehouse": warehouse,
                    "purchase_description": "Food-grade stainless-steel measuring cup with long handle.",
                    "purchase_remarks": "Verify dimensions before creating the Item.",
                    "publish_item_to_k95": 1,
                    "pending_mr_qty": 4,
                    "processing_status": "PENDING_ITEM_VERIFICATION",
                },
            ],
        }
    ).insert(ignore_permissions=True)

    svg = b"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"720\" height=\"480\" viewBox=\"0 0 720 480\"><rect width=\"720\" height=\"480\" fill=\"#f5f7fa\"/><rect x=\"275\" y=\"95\" width=\"170\" height=\"230\" rx=\"28\" fill=\"#cbd5e1\" stroke=\"#334155\" stroke-width=\"8\"/><path d=\"M445 145h90c65 0 65 125 0 125h-90\" fill=\"none\" stroke=\"#334155\" stroke-width=\"20\"/><path d=\"M305 360h110\" stroke=\"#334155\" stroke-width=\"12\" stroke-linecap=\"round\"/><text x=\"360\" y=\"420\" text-anchor=\"middle\" font-family=\"Arial\" font-size=\"28\" fill=\"#0f172a\">Sample Measuring Cup</text></svg>"""
    file_doc = save_file(
        "sample-measuring-cup.svg",
        svg,
        "New Item Material Request",
        nimr.name,
        is_private=1,
    )

    nimr.reload()
    new_line = next(row for row in nimr.items if row.external_line_id.endswith("L002"))
    new_line.primary_image = file_doc.file_url
    nimr.append(
        "attachments",
        {
            "external_attachment_id": "ATT-K95-SAMPLE-L002-01",
            "external_line_id": new_line.external_line_id,
            "media_type": "IMAGE",
            "file_name": file_doc.file_name,
            "mime_type": "image/svg+xml",
            "file_size": len(svg),
            "file_hash": hashlib.sha256(svg).hexdigest(),
            "external_file_url": "https://k95.example.test/files/sample-measuring-cup.svg",
            "file": file_doc.file_url,
            "caption": "Reference image supplied by the K95 requester",
            "is_primary_image": 1,
            "download_status": "DOWNLOADED",
        },
    )
    nimr.save(ignore_permissions=True)

    inbound.db_set(
        {
            "status": "PROCESSED",
            "processed_at": now_datetime(),
            "nimr": nimr.name,
        },
        update_modified=False,
    )
    frappe.db.commit()
    return {
        "created": True,
        "nimr": nimr.name,
        "inbound_event": inbound.name,
        "item_lines": len(nimr.items),
        "attachments": len(nimr.attachments),
        "existing_item": item_code,
        "warehouse": warehouse,
    }
