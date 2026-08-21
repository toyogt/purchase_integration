import hashlib
import json

import frappe
from frappe.utils import now_datetime
from frappe.utils.file_manager import save_file


PR_ID = "K95-PI-DEMO-PR-0008"
EVENT_ID = "evt_K95-PI-DEMO-PR-0008_erp_release_v1"


def _svg(label, shape_color):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="720" height="480" viewBox="0 0 720 480"><rect width="720" height="480" fill="#f8fafc"/><rect x="235" y="90" width="250" height="250" rx="32" fill="{shape_color}" stroke="#334155" stroke-width="8"/><path d="M285 165h150M285 220h150M285 275h100" stroke="#fff" stroke-width="18" stroke-linecap="round"/><text x="360" y="410" text-anchor="middle" font-family="Arial" font-size="26" fill="#0f172a">{label}</text></svg>""".encode()


def run():
    existing = frappe.db.get_value(
        "New Item Material Request", {"external_pr_id": PR_ID}, "name"
    )
    if existing:
        demo = frappe.get_doc("New Item Material Request", existing)
        if frappe.db.exists("UOM", "Nos"):
            for row in demo.items:
                if row.item_source == "NEW" and not row.erpnext_item:
                    row.requested_uom = "Nos"
                    row.purchase_uom = "Nos"
            demo.save(ignore_permissions=True)
            frappe.db.commit()
        return {"created": False, "nimr": existing, "reason": "demo already exists and was refreshed"}

    source = frappe.get_doc("New Item Material Request", "K95-TEST-PR-0003")
    demo = frappe.copy_doc(source)
    demo.pr_unique_id = PR_ID
    demo.external_pr_id = PR_ID
    demo.external_document_id = "k95_demo_document_004"
    demo.correlation_id = f"corr_{PR_ID}"
    demo.source_event_id = EVENT_ID
    demo.idempotency_key = f"{PR_ID}:ERP_RELEASE:1"
    demo.request_title = "Demo PR: one existing and two new Items"
    demo.request_date = now_datetime()
    demo.submitted_at = now_datetime()
    demo.store_verified_at = now_datetime()
    demo.status = "Draft"
    demo.processing_status = "Pending Item Creation"
    demo.total_lines = 3
    demo.ready_for_mr_lines = 1
    demo.pending_item_verification_lines = 2
    demo.mr_created_lines = 0
    demo.ordered_lines = 0
    demo.failed_lines = 0
    demo.received_at = now_datetime()
    demo.last_processed_at = now_datetime()
    demo.inbound_event = None
    demo.set("attachments", [])
    demo.set("allocations", [])

    existing_row = demo.items[0]
    existing_row.external_line_id = f"{PR_ID}-L001"
    existing_row.line_number = 1
    existing_row.mr_created_qty = 0
    existing_row.pending_mr_qty = existing_row.final_purchase_qty
    existing_row.ordered_qty = 0
    existing_row.pending_order_qty = 0
    existing_row.processing_status = "READY_FOR_MR"

    new_row = demo.items[1]
    new_row.external_line_id = f"{PR_ID}-L002"
    new_row.line_number = 2
    new_row.requested_item_name = "Food-Grade Stainless-Steel Sampling Scoop"
    new_row.requested_description = "Long-handle stainless-steel sampling scoop for production tanks."
    new_row.requirement = "Quality sampling equipment"
    new_row.need_purpose = "Used by the quality team to collect safe production samples."
    new_row.purchase_description = new_row.requested_description
    new_row.primary_image = None
    new_row.erpnext_item = None
    new_row.item_resolution_status = "PENDING_ITEM_CREATION"
    new_row.processing_status = "PENDING_ITEM_VERIFICATION"
    new_row.publish_item_to_k95 = 1
    if frappe.db.exists("UOM", "Nos"):
        new_row.requested_uom = "Nos"
        new_row.purchase_uom = "Nos"

    third = demo.append(
        "items",
        {
            "external_line_id": f"{PR_ID}-L003",
            "line_number": 3,
            "item_source": "NEW",
            "requested_item_name": "Food-Grade Ingredient Storage Bin",
            "requested_description": "Food-safe storage bin with lid, approximately 50-litre capacity.",
            "requirement": "Ingredient storage",
            "need_purpose": "Required to keep production ingredients sealed and identified.",
            "requested_qty": 3,
            "hod_approved_qty": 3,
            "store_verified_qty": 3,
            "purchase_required_qty": 3,
            "requested_uom": new_row.requested_uom,
            "requested_required_by": "2026-09-05",
            "hod_required_by": "2026-09-05",
            "store_required_by": "2026-09-05",
            "current_stock_qty": 0,
            "already_on_order_qty": 0,
            "calculated_shortage_qty": 3,
            "stock_snapshot_at": now_datetime(),
            "store_line_remarks": "No equivalent Item found in ERPNext.",
            "item_resolution_status": "PENDING_ITEM_CREATION",
            "publish_item_to_k95": 1,
            "final_purchase_qty": 3,
            "purchase_uom": new_row.purchase_uom,
            "conversion_factor": 1,
            "schedule_date": "2026-09-05",
            "target_warehouse": new_row.target_warehouse,
            "purchase_description": "Food-safe storage bin with lid, approximately 50-litre capacity.",
            "purchase_remarks": "Confirm dimensions before purchase.",
            "pending_mr_qty": 3,
            "processing_status": "PENDING_ITEM_VERIFICATION",
        },
    )

    payload = {
        "event_id": EVENT_ID,
        "event_type": "purchase_request.ready_for_erpnext",
        "event_version": "1.0",
        "idempotency_key": demo.idempotency_key,
        "correlation_id": demo.correlation_id,
        "purchase_request": {
            "pr_number": PR_ID,
            "company": demo.company,
            "requester_name": demo.requester_name,
            "department": demo.department_name,
        },
        "items": [
            {
                "line_id": row.external_line_id,
                "item_source": row.item_source,
                "item_code": row.external_item_code,
                "item_name": row.requested_item_name,
                "description": row.requested_description,
                "requirement": row.requirement,
                "need_purpose": row.need_purpose,
                "purchase_required_qty": row.purchase_required_qty,
                "uom": row.requested_uom,
                "required_by": row.store_required_by,
            }
            for row in demo.items
        ],
    }
    payload_text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    payload_hash = hashlib.sha256(payload_text.encode()).hexdigest()
    demo.source_payload_hash = payload_hash

    inbound = frappe.get_doc(
        {
            "doctype": "K95 Inbound Event",
            "event_id": EVENT_ID,
            "idempotency_key": demo.idempotency_key,
            "event_type": payload["event_type"],
            "event_version": "1.0",
            "correlation_id": demo.correlation_id,
            "external_pr_id": PR_ID,
            "payload": payload_text,
            "payload_hash": payload_hash,
            "status": "PROCESSING",
            "attempt_count": 1,
            "received_at": now_datetime(),
        }
    ).insert(ignore_permissions=True)
    demo.inbound_event = inbound.name
    demo.insert(ignore_permissions=True)

    images = [
        (new_row.external_line_id, "sampling-scoop.svg", "Sampling Scoop", "#0ea5e9"),
        (third.external_line_id, "ingredient-bin.svg", "Ingredient Storage Bin", "#22c55e"),
    ]
    demo.reload()
    for external_line_id, filename, label, color in images:
        content = _svg(label, color)
        file_doc = save_file(filename, content, demo.doctype, demo.name, is_private=1)
        row = next(item for item in demo.items if item.external_line_id == external_line_id)
        row.primary_image = file_doc.file_url
        demo.append(
            "attachments",
            {
                "external_attachment_id": f"ATT-{external_line_id}-01",
                "external_line_id": external_line_id,
                "media_type": "IMAGE",
                "file_name": file_doc.file_name,
                "mime_type": "image/svg+xml",
                "file_size": len(content),
                "file_hash": hashlib.sha256(content).hexdigest(),
                "file": file_doc.file_url,
                "caption": f"Reference image for {label}",
                "is_primary_image": 1,
                "download_status": "DOWNLOADED",
            },
        )
    demo.save(ignore_permissions=True)
    inbound.db_set(
        {"status": "PROCESSED", "processed_at": now_datetime(), "nimr": demo.name},
        update_modified=False,
    )
    frappe.db.commit()
    return {
        "created": True,
        "nimr": demo.name,
        "inbound_event": inbound.name,
        "items": len(demo.items),
        "existing_items": 1,
        "new_items": 2,
        "attachments": len(demo.attachments),
    }


def dry_test_material_request(nimr_name="K95-PI-DEMO-PR-0005"):
    """Exercise real MR creation and roll back every database change."""
    from purchase_integration.nimr import create_material_request

    nimr = frappe.get_doc("New Item Material Request", nimr_name)
    row = next(
        (
            item
            for item in nimr.items
            if item.erpnext_item
            and max((item.final_purchase_qty or 0) - (item.mr_created_qty or 0), 0) > 0
        ),
        None,
    )
    if not row:
        return {"passed": False, "reason": "No eligible unconverted line is available."}

    savepoint = "purchase_integration_mr_dry_test"
    original_mr_qty = row.mr_created_qty or 0
    frappe.db.savepoint(savepoint)
    try:
        result = create_material_request(nimr.name, [row.name])
        mr_name = result["material_request"]
        mr = frappe.get_doc("Material Request", mr_name)
        allocation = frappe.db.get_value(
            "NIMR Conversion Allocation",
            {"parent": nimr.name, "material_request": mr_name, "nimr_item_row_id": row.name},
            ["name", "material_request_item_id", "mr_qty"],
            as_dict=True,
        )
        updated_row = frappe.db.get_value(
            "NIMR Item",
            row.name,
            ["mr_created_qty", "pending_mr_qty", "processing_status"],
            as_dict=True,
        )
        parent_progress = frappe.db.get_value(
            "New Item Material Request", nimr.name, "processing_status"
        )
        try:
            create_material_request(nimr.name, [row.name])
            duplicate_blocked = False
        except frappe.ValidationError:
            duplicate_blocked = True
        checks = {
            "mr_created": bool(mr.name),
            "one_selected_item_only": len(mr.items) == 1,
            "correct_item": mr.items[0].item_code == row.erpnext_item,
            "allocation_created": bool(allocation),
            "allocation_links_mr_item": bool(
                allocation and allocation.material_request_item_id == mr.items[0].name
            ),
            "line_marked_converted": bool(
                updated_row
                and updated_row.mr_created_qty > original_mr_qty
                and updated_row.pending_mr_qty == 0
                and updated_row.processing_status == "MR_CREATED"
            ),
            "duplicate_same_line_qty_date_blocked": duplicate_blocked,
            "parent_marked_partially_mr_created": parent_progress == "Partially MR Created",
        }
        tested = {
            "passed": all(checks.values()),
            "nimr": nimr.name,
            "line": row.external_line_id,
            "temporary_material_request": mr_name,
            "checks": checks,
        }
    finally:
        frappe.db.rollback(save_point=savepoint)

    tested["rollback_verified"] = not frappe.db.exists("Material Request", mr_name)
    tested["passed"] = tested["passed"] and tested["rollback_verified"]
    return tested
