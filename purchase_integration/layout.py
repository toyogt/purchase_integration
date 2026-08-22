import frappe


def _ensure_layout_fields(doc, definitions):
    existing = {row.fieldname for row in doc.fields}
    for definition in definitions:
        if definition["fieldname"] not in existing:
            doc.append("fields", definition)


def _reorder(doc, preferred_order):
    rank = {fieldname: index for index, fieldname in enumerate(preferred_order)}
    original_rank = {row.fieldname: index for index, row in enumerate(doc.fields)}
    rows = sorted(
        list(doc.fields),
        key=lambda row: (
            rank.get(row.fieldname, len(preferred_order)),
            original_rank.get(row.fieldname, 0),
        ),
    )
    doc.set("fields", rows)
    for index, row in enumerate(doc.fields, 1):
        row.idx = index


def _configure_parent():
    doc = frappe.get_doc("DocType", "New Item Material Request")
    _ensure_layout_fields(
        doc,
        [
            {"fieldname": "purchase_request_tab", "label": "Purchase Request", "fieldtype": "Tab Break"},
            {"fieldname": "request_overview_section", "label": "Request Overview", "fieldtype": "Section Break"},
            {"fieldname": "request_overview_column", "fieldtype": "Column Break"},
            {"fieldname": "summary_column", "fieldtype": "Column Break"},
            {"fieldname": "approval_attachments_tab", "label": "Approval & Attachments", "fieldtype": "Tab Break"},
            {"fieldname": "requester_column", "fieldtype": "Column Break"},
            {"fieldname": "store_verification_column", "fieldtype": "Column Break"},
            {"fieldname": "integration_tab", "label": "Integration", "fieldtype": "Tab Break"},
        ],
    )

    by_name = {row.fieldname: row for row in doc.fields}
    for fieldname in ("workflow_state", "status"):
        if fieldname in by_name:
            by_name[fieldname].hidden = 1

    if "request_title" in by_name:
        by_name["request_title"].bold = 1
    if "external_pr_id" in by_name:
        by_name["external_pr_id"].bold = 1
        by_name["external_pr_id"].in_standard_filter = 1
    if "processing_status" in by_name:
        by_name["processing_status"].label = "NIMR Progress"
        by_name["processing_status"].options = "Pending Item Creation\nReady for MR\nPartially MR Created\nMR Fully Created\nPartially Ordered\nFully Ordered\nError"
        by_name["processing_status"].default = "Pending Item Creation"
        by_name["processing_status"].bold = 1
        by_name["processing_status"].in_standard_filter = 1
    if "pending_item_verification_lines" in by_name:
        by_name["pending_item_verification_lines"].label = "Pending Item Creation"
    if "mr_created_lines" in by_name:
        by_name["mr_created_lines"].label = "MR Created Lines"
    if "ordered_lines" in by_name:
        by_name["ordered_lines"].label = "Fully Ordered Lines"
    if "items_section" in by_name:
        by_name["items_section"].label = "Purchase Items"
    for fieldname in ("requester_section", "verification_section", "attachments_section"):
        if fieldname in by_name:
            by_name[fieldname].collapsible = 1
    if "allocations_section" in by_name:
        by_name["allocations_section"].collapsible = 1
        by_name["allocations_section"].collapsible_depends_on = "eval:doc.allocations && doc.allocations.length"
    if "integration_section" in by_name:
        by_name["integration_section"].label = "Technical Integration Details"
        by_name["integration_section"].collapsible = 1

    preferred = [
        "purchase_request_tab",
        "request_overview_section",
        "external_pr_id",
        "request_title",
        "company",
        "priority",
        "request_overview_column",
        "requester_name",
        "department_name",
        "request_date",
        "submitted_at",
        "store_verified_at",
        "summary_section",
        "processing_status",
        "total_lines",
        "ready_for_mr_lines",
        "summary_column",
        "pending_item_verification_lines",
        "mr_created_lines",
        "ordered_lines",
        "failed_lines",
        "items_section",
        "items",
        "approval_attachments_tab",
        "requester_section",
        "requester_user_id",
        "requester_employee_id",
        "requester_column",
        "requester_email",
        "requested_on_behalf_of",
        "verification_section",
        "hod_status",
        "hod_approved_by",
        "hod_approved_by_email",
        "hod_approved_at",
        "hod_remarks",
        "store_verification_column",
        "store_status",
        "store_verified_by",
        "store_verified_by_email",
        "store_remarks",
        "attachments_section",
        "attachments",
        "allocations_section",
        "allocations",
        "integration_tab",
        "integration_section",
        "integration_status",
        "inbound_event",
        "received_at",
        "last_processed_at",
        "last_sync_at",
        "last_integration_error",
        "k95_request_section",
        "external_document_id",
        "correlation_id",
        "source_event_id",
        "source_event_version",
        "source_record_version",
        "idempotency_key",
        "source_system",
        "source_payload_hash",
    ]
    _reorder(doc, preferred)
    doc.save(ignore_permissions=True)


def _configure_item_child():
    doc = frappe.get_doc("DocType", "NIMR Item")
    _ensure_layout_fields(
        doc,
        [
            {"fieldname": "source_column", "fieldtype": "Column Break"},
            {"fieldname": "request_quantities_column", "fieldtype": "Column Break"},
            {"fieldname": "store_snapshot_column", "fieldtype": "Column Break"},
            {"fieldname": "erp_purchase_column", "fieldtype": "Column Break"},
            {"fieldname": "progress_column", "fieldtype": "Column Break"},
        ],
    )
    by_name = {row.fieldname: row for row in doc.fields}

    grid = {
        "line_number": 1,
        "requested_item_name": 2,
        "erpnext_item": 2,
        "create_item_action": 1,
        "final_purchase_qty": 1,
        "purchase_uom": 1,
        "schedule_date": 1,
        "item_resolution_status": 2,
    }
    for row in doc.fields:
        row.in_list_view = 0
        row.columns = 0
    for fieldname, columns in grid.items():
        if fieldname in by_name:
            by_name[fieldname].in_list_view = 1
            by_name[fieldname].columns = columns

    for fieldname in ("requested_description", "requirement", "need_purpose", "store_line_remarks", "purchase_description", "purchase_remarks"):
        if fieldname in by_name:
            by_name[fieldname].columns = 12
    by_name["requested_details_section"].label = "Original K95 Request"
    by_name["store_snapshot_section"].label = "Store Verification Snapshot"
    by_name["erp_processing_section"].label = "ERPNext Purchase Details"
    by_name["source_identity_section"].collapsible = 1
    by_name["store_snapshot_section"].collapsible = 1
    by_name["progress_section"].collapsible = 1

    preferred = [
        "source_identity_section",
        "external_line_id",
        "line_number",
        "source_column",
        "item_source",
        "external_item_code",
        "k95_item_id",
        "requested_details_section",
        "requested_item_name",
        "requested_description",
        "requirement",
        "need_purpose",
        "request_quantities_column",
        "requested_qty",
        "hod_approved_qty",
        "store_verified_qty",
        "purchase_required_qty",
        "requested_uom",
        "requested_required_by",
        "hod_required_by",
        "store_required_by",
        "store_snapshot_section",
        "current_stock_qty",
        "already_on_order_qty",
        "calculated_shortage_qty",
        "store_snapshot_column",
        "stock_snapshot_at",
        "store_line_remarks",
        "erp_processing_section",
        "erpnext_item",
        "create_item_action",
        "item_resolution_status",
        "resolution_method",
        "primary_image",
        "publish_item_to_k95",
        "erp_purchase_column",
        "final_purchase_qty",
        "purchase_uom",
        "conversion_factor",
        "schedule_date",
        "target_warehouse",
        "purchase_description",
        "purchase_remarks",
        "progress_section",
        "mr_created_qty",
        "pending_mr_qty",
        "progress_column",
        "ordered_qty",
        "pending_order_qty",
        "processing_status",
        "resolved_by",
        "resolved_at",
        "last_processing_error",
    ]
    _reorder(doc, preferred)
    doc.save(ignore_permissions=True)


def _configure_attachment_child():
    doc = frappe.get_doc("DocType", "NIMR Item Attachment")
    by_name = {row.fieldname: row for row in doc.fields}
    grid = {
        "external_line_id": 2,
        "media_type": 1,
        "file_name": 3,
        "caption": 2,
        "download_status": 1,
    }
    for row in doc.fields:
        row.in_list_view = 0
        row.columns = 0
    for fieldname, columns in grid.items():
        if fieldname in by_name:
            by_name[fieldname].in_list_view = 1
            by_name[fieldname].columns = columns
    doc.save(ignore_permissions=True)


def _configure_allocation_child():
    doc = frappe.get_doc("DocType", "NIMR Conversion Allocation")
    by_name = {row.fieldname: row for row in doc.fields}
    grid = {
        "external_line_id": 2,
        "item_code": 2,
        "material_request": 2,
        "mr_qty": 1,
        "purchase_order": 2,
        "ordered_qty": 1,
        "status": 2,
    }
    for row in doc.fields:
        row.in_list_view = 0
        row.columns = 0
    for fieldname, columns in grid.items():
        if fieldname in by_name:
            by_name[fieldname].in_list_view = 1
            by_name[fieldname].columns = columns
    doc.save(ignore_permissions=True)


def run():
    _configure_parent()
    _configure_item_child()
    _configure_attachment_child()
    _configure_allocation_child()
    frappe.clear_cache(doctype="New Item Material Request")
    frappe.clear_cache(doctype="NIMR Item")
    frappe.db.commit()
    return {
        "parent_tabs": ["Purchase Request", "Approval & Attachments", "Integration"],
        "configured_doctypes": [
            "New Item Material Request",
            "NIMR Item",
            "NIMR Item Attachment",
            "NIMR Conversion Allocation",
        ],
    }
