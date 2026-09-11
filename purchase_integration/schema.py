import frappe


MODULE = "Purchase Integration"
PARENT = "New Item Material Request"


def _field(fieldname, label, fieldtype, **kwargs):
    value = {"fieldname": fieldname, "label": label, "fieldtype": fieldtype}
    value.update(kwargs)
    return value


def _ensure_doctype(name, *, istable=False, fields=None):
    exists = frappe.db.exists("DocType", name)
    if exists:
        doc = frappe.get_doc("DocType", name)
    else:
        doc = frappe.get_doc(
            {
                "doctype": "DocType",
                "name": name,
                "module": MODULE,
                "custom": 1,
                "istable": int(istable),
                "engine": "InnoDB",
            }
        )

    doc.module = MODULE

    existing = {row.fieldname for row in doc.fields}
    for definition in fields or []:
        if definition["fieldname"] not in existing:
            doc.append("fields", definition)

    if not exists:
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)


def _ensure_parent_fields(fields):
    doc = frappe.get_doc("DocType", PARENT)
    doc.module = MODULE
    existing = {row.fieldname: row for row in doc.fields}
    for definition in fields:
        if definition["fieldname"] not in existing:
            doc.append("fields", definition)
            continue
        row = existing[definition["fieldname"]]
        for property_name in ("label", "options", "default", "read_only", "in_list_view"):
            if property_name in definition:
                setattr(row, property_name, definition[property_name])
    doc.track_changes = 1
    doc.save(ignore_permissions=True)


def _ensure_parent_doctype():
    """Make installation independent of a manually-created NIMR DocType."""
    exists = frappe.db.exists("DocType", PARENT)
    if exists:
        doc = frappe.get_doc("DocType", PARENT)
    else:
        doc = frappe.get_doc({
            "doctype": "DocType", "name": PARENT, "module": MODULE, "custom": 1,
            "engine": "InnoDB", "track_changes": 1, "autoname": "field:external_pr_id",
            "permissions": [
                {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "submit": 1, "cancel": 1, "amend": 1, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1},
                {"role": "Purchase User", "read": 1, "write": 1, "create": 1, "submit": 1, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1},
                {"role": "Purchase Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "submit": 1, "cancel": 1, "amend": 1, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1},
            ],
        })
    doc.module = MODULE
    doc.track_changes = 1
    doc.autoname = "field:external_pr_id"
    doc.is_submittable = 1
    doc.title_field = "external_pr_id"
    doc.search_fields = "external_pr_id,request_title,requester_name"
    if not exists:
        doc.append("fields", _field("external_pr_id", "K95 Purchase Request", "Data", unique=1, read_only=1, in_list_view=1))
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)


def _create_child_doctypes():
    _ensure_doctype(
        "NIMR Item",
        istable=True,
        fields=[
            _field("source_identity_section", "K95 Source", "Section Break"),
            _field("external_line_id", "K95 Line ID", "Data", reqd=1, in_list_view=1),
            _field("line_number", "Line", "Int"),
            _field("item_source", "Item Source", "Select", options="MASTER\nNEW"),
            _field("external_item_code", "K95 Item Code", "Data"),
            _field("k95_item_id", "K95 Item ID", "Data"),
            _field("requested_details_section", "Original Request", "Section Break"),
            _field("requested_item_name", "Requested Item", "Data", reqd=1, in_list_view=1),
            _field("requested_description", "Description", "Small Text"),
            _field("requirement", "Requirement", "Small Text"),
            _field("need_purpose", "Need / Purpose", "Small Text"),
            _field("requested_qty", "Requested Qty", "Float", precision="3"),
            _field("hod_approved_qty", "HOD Approved Qty", "Float", precision="3"),
            _field("store_verified_qty", "Store Verified Qty", "Float", precision="3"),
            _field("purchase_required_qty", "Purchase Required Qty", "Float", reqd=1, precision="3"),
            _field("requested_uom", "Requested UOM", "Data"),
            _field("requested_required_by", "Requested By Date", "Date"),
            _field("hod_required_by", "HOD Required By", "Date"),
            _field("store_required_by", "Store Required By", "Date"),
            _field("store_snapshot_section", "Store Verification", "Section Break"),
            _field("current_stock_qty", "Stock Snapshot", "Float", precision="3"),
            _field("already_on_order_qty", "Already On Order", "Float", precision="3"),
            _field("calculated_shortage_qty", "Calculated Shortage", "Float", precision="3"),
            _field("stock_snapshot_at", "Stock Snapshot On", "Datetime"),
            _field("store_line_remarks", "Store Remarks", "Small Text"),
            _field("erp_processing_section", "ERPNext Purchase Details", "Section Break"),
            _field("erpnext_item", "ERPNext Item", "Link", options="Item", in_list_view=1),
            _field(
                "create_item_action",
                "Create Item",
                "Button",
                depends_on="eval:!doc.erpnext_item",
                in_list_view=1,
            ),
            _field(
                "item_resolution_status",
                "Item Status",
                "Select",
                options="NOT_CHECKED\nAUTO_MATCHED\nMANUALLY_MATCHED\nPENDING_ITEM_CREATION\nNEW_ITEM_CREATED\nDUPLICATE_REVIEW_REQUIRED\nERROR",
                default="NOT_CHECKED",
                in_list_view=1,
            ),
            _field("resolution_method", "Resolution Method", "Data"),
            _field("final_purchase_qty", "Final Purchase Qty", "Float", reqd=1, precision="3", in_list_view=1),
            _field("purchase_uom", "Purchase UOM", "Link", options="UOM", in_list_view=1),
            _field("conversion_factor", "Conversion Factor", "Float", default="1", precision="6"),
            _field("schedule_date", "Required By", "Date", in_list_view=1),
            _field("target_warehouse", "Target Warehouse", "Link", options="Warehouse"),
            _field("purchase_description", "Purchase Description", "Small Text"),
            _field("purchase_remarks", "Purchase Remarks", "Small Text"),
            _field("primary_image", "Primary Image", "Attach Image"),
            _field("publish_item_to_k95", "Publish Item to K95", "Check", default="1"),
            _field("progress_section", "Processing Progress", "Section Break"),
            _field("mr_created_qty", "MR Created Qty", "Float", read_only=1, precision="3"),
            _field("ordered_qty", "Ordered Qty", "Float", read_only=1, precision="3"),
            _field("pending_mr_qty", "Pending MR Qty", "Float", read_only=1, precision="3"),
            _field("pending_order_qty", "Pending Order Qty", "Float", read_only=1, precision="3"),
            _field(
                "processing_status",
                "Processing Status",
                "Select",
                options="PENDING_ITEM_VERIFICATION\nREADY_FOR_MR\nPARTIALLY_CONVERTED\nMR_CREATED\nPARTIALLY_ORDERED\nORDERED\nERROR",
                default="PENDING_ITEM_VERIFICATION",
                read_only=1,
                in_list_view=1,
            ),
            _field("resolved_by", "Resolved By", "Link", options="User", read_only=1),
            _field("resolved_at", "Resolved On", "Datetime", read_only=1),
            _field("last_processing_error", "Processing Error", "Small Text", read_only=1),
        ],
    )

    _ensure_doctype(
        "NIMR Item Attachment",
        istable=True,
        fields=[
            _field("external_attachment_id", "K95 Attachment ID", "Data", in_list_view=1),
            _field("external_line_id", "K95 Line ID", "Data", in_list_view=1),
            _field("media_type", "Media Type", "Select", options="IMAGE\nVIDEO\nDOCUMENT", in_list_view=1),
            _field("file_name", "File Name", "Data", in_list_view=1),
            _field("mime_type", "MIME Type", "Data"),
            _field("file_size", "File Size", "Int"),
            _field("file_hash", "SHA-256", "Data"),
            _field("external_file_url", "Source URL", "Small Text"),
            _field("file", "ERPNext File", "Attach"),
            _field("caption", "Caption", "Data"),
            _field("is_primary_image", "Primary Image", "Check"),
            _field("download_status", "Download Status", "Select", options="PENDING\nDOWNLOADED\nFAILED", default="PENDING"),
            _field("download_error", "Download Error", "Small Text"),
        ],
    )

    _ensure_doctype(
        "NIMR Conversion Allocation",
        istable=True,
        fields=[
            _field("allocation_id", "Allocation ID", "Data", in_list_view=1),
            _field("nimr_item_row_id", "NIMR Item Row", "Data"),
            _field("external_line_id", "K95 Line ID", "Data", in_list_view=1),
            _field("item_code", "Item", "Link", options="Item", in_list_view=1),
            _field("material_request", "Material Request", "Link", options="Material Request", in_list_view=1),
            _field("legacy_material_request_reference", "Legacy MR Reference", "Data", read_only=1),
            _field("material_request_item_id", "MR Item Row", "Data"),
            _field("mr_qty", "MR Quantity", "Float", precision="3"),
            _field("schedule_date", "Required By", "Date"),
            _field("conversion_key", "Conversion Key", "Data", unique=1, read_only=1),
            _field("purchase_order", "Purchase Order", "Link", options="Purchase Order", in_list_view=1),
            _field("purchase_order_item_id", "PO Item Row", "Data"),
            _field("ordered_qty", "Ordered Quantity", "Float", precision="3"),
            _field("status", "Status", "Select", options="MR_CREATED\nPARTIALLY_ORDERED\nORDERED\nCANCELLED", in_list_view=1),
        ],
    )


def _create_inbound_event_doctype():
    _ensure_doctype(
        "K95 Inbound Event",
        fields=[
            _field("event_section", "Event", "Section Break"),
            _field("event_id", "Event ID", "Data", reqd=1, unique=1, in_list_view=1),
            _field("idempotency_key", "Idempotency Key", "Data", reqd=1, unique=1),
            _field("event_type", "Event Type", "Data", reqd=1, in_list_view=1),
            _field("event_version", "Event Version", "Data"),
            _field("correlation_id", "Correlation ID", "Data"),
            _field("external_pr_id", "K95 Purchase Request", "Data", in_list_view=1),
            _field("payload", "Payload", "Long Text", reqd=1),
            _field("payload_hash", "Payload Hash", "Data"),
            _field("processing_section", "Processing", "Section Break"),
            _field("status", "Status", "Select", options="RECEIVED\nPROCESSING\nPROCESSED\nPARTIALLY_PROCESSED\nREJECTED\nFAILED", default="RECEIVED", in_list_view=1),
            _field("attempt_count", "Attempt Count", "Int", default="0"),
            _field("received_at", "Received On", "Datetime"),
            _field("processed_at", "Processed On", "Datetime"),
            _field("nimr", "NIMR", "Link", options=PARENT),
            _field("last_error", "Last Error", "Long Text"),
        ],
    )


def _create_integration_settings():
    name = "Purchase Integration Settings"
    exists = frappe.db.exists("DocType", name)
    if exists:
        doc = frappe.get_doc("DocType", name)
    else:
        doc = frappe.get_doc(
            {
                "doctype": "DocType",
                "name": name,
                "module": MODULE,
                "custom": 1,
                "issingle": 1,
                "track_changes": 1,
                "engine": "InnoDB",
            }
        )

    doc.module = MODULE
    doc.issingle = 1
    definitions = [
        _field("general_section", "Integration", "Section Break"),
        _field("integration_enabled", "Enable K95 Integration", "Check", default="0"),
        _field("environment", "Environment", "Select", options="Development\nStaging\nProduction", default="Development", reqd=1),
        _field("company", "Company", "Link", options="Company", reqd=1),
        _field("general_column", "", "Column Break"),
        _field("erpnext_base_url", "ERPNext Public Base URL", "Data", description="Example: https://erpnext.k95foods.com"),
        _field("k95_base_url", "K95 API Base URL", "Data", reqd=1, description="Do not include a UI route such as /SupplierManager."),
        _field("verify_ssl", "Verify SSL Certificate", "Check", default="1"),
        _field("outbound_section", "K95 Outbound Endpoints", "Section Break", collapsible=1),
        _field("item_upsert_path", "Item Upsert Path", "Data", default="/api/erpnext/items/upsert"),
        _field("item_mapping_path", "Item Mapping Path", "Data", default="/api/erpnext/items/map"),
        _field("supplier_upsert_path", "Supplier Upsert Path", "Data", default="/api/erpnext/suppliers/upsert"),
        _field("material_request_upsert_path", "Material Request Upsert Path", "Data", default="/api/erpnext/material-requests/upsert"),
        _field("outbound_column", "", "Column Break"),
        _field("purchase_order_upsert_path", "Purchase Order Upsert Path", "Data", default="/api/erpnext/purchase-orders/upsert"),
        _field("purchase_request_status_path", "Purchase Request Status Path", "Data", default="/api/erpnext/purchase-request-status/upsert"),
        _field("master_data_upsert_path", "Master Data Upsert Path", "Data", default="/api/erpnext/master-data/upsert"),
        _field("attachment_upsert_path", "Attachment Upsert Path", "Data", default="/api/erpnext/attachments/upsert"),
        _field("authentication_section", "Authentication", "Section Break", collapsible=1),
        _field("outbound_auth_type", "ERPNext to K95 Authentication", "Select", options="HMAC-SHA256\nBearer Token", default="HMAC-SHA256", reqd=1),
        _field("outbound_key_id", "K95 Key ID", "Data"),
        _field("outbound_hmac_secret", "K95 HMAC Secret", "Password"),
        _field("outbound_bearer_token", "K95 Bearer Token", "Password"),
        _field("authentication_column", "", "Column Break"),
        _field("inbound_auth_type", "K95 to ERPNext Authentication", "Select", options="HMAC-SHA256\nERPNext API Token", default="HMAC-SHA256", reqd=1),
        _field("inbound_key_id", "Inbound Key ID", "Data"),
        _field("inbound_hmac_secret", "Inbound HMAC Secret", "Password"),
        _field("allowed_source_ips", "Allowed Source IPs", "Small Text", description="Optional comma-separated IPs or CIDR ranges."),
        _field("delivery_section", "Delivery and Retry", "Section Break", collapsible=1),
        _field("request_timeout_seconds", "Request Timeout (seconds)", "Int", default="30", reqd=1),
        _field("replay_window_seconds", "Replay Window (seconds)", "Int", default="300", reqd=1),
        _field("max_retry_attempts", "Maximum Retry Attempts", "Int", default="10", reqd=1),
        _field("initial_retry_delay_seconds", "Initial Retry Delay (seconds)", "Int", default="60", reqd=1),
        _field("delivery_column", "", "Column Break"),
        _field("retry_backoff_multiplier", "Retry Backoff Multiplier", "Float", default="2", precision="2"),
        _field("maximum_retry_delay_seconds", "Maximum Retry Delay (seconds)", "Int", default="3600"),
        _field("master_reconciliation_enabled", "Enable Daily Master Reconciliation", "Check", default="1"),
        _field("status_section", "Connection Status", "Section Break", collapsible=1),
        _field("last_connection_status", "Last Connection Status", "Select", options="Not Tested\nSuccessful\nFailed", default="Not Tested", read_only=1),
        _field("last_connection_at", "Last Connection Test", "Datetime", read_only=1),
        _field("last_successful_sync_at", "Last Successful Sync", "Datetime", read_only=1),
        _field("last_connection_error", "Last Connection Error", "Long Text", read_only=1),
    ]

    existing_fields = {row.fieldname: row for row in doc.fields}
    for definition in definitions:
        if definition["fieldname"] not in existing_fields:
            doc.append("fields", definition)
            continue
        row = existing_fields[definition["fieldname"]]
        for property_name, value in definition.items():
            if property_name != "fieldname":
                setattr(row, property_name, value)

    if not exists:
        doc.append(
            "permissions",
            {"role": "System Manager", "read": 1, "write": 1, "create": 1},
        )
        doc.insert(ignore_permissions=True)
    else:
        if not any(permission.role == "System Manager" for permission in doc.permissions):
            doc.append(
                "permissions",
                {"role": "System Manager", "read": 1, "write": 1, "create": 1},
            )
        doc.save(ignore_permissions=True)


def _create_outbound_event_doctype():
    _ensure_doctype(
        "K95 Outbound Event",
        fields=[
            _field("event_section", "Event", "Section Break"),
            _field("event_id", "Event ID", "Data", reqd=1, unique=1, in_list_view=1),
            _field("event_type", "Event Type", "Data", reqd=1, in_list_view=1),
            _field("event_version", "Event Version", "Int", default="1"),
            _field("idempotency_key", "Idempotency Key", "Data", reqd=1, unique=1),
            _field("correlation_id", "Correlation ID", "Data"),
            _field("aggregate_type", "Aggregate Type", "Data", in_list_view=1),
            _field("aggregate_id", "Aggregate ID", "Data", in_list_view=1),
            _field("external_pr_id", "K95 Purchase Request", "Data"),
            _field("external_line_id", "K95 Purchase Request Line", "Data"),
            _field("endpoint_path", "Endpoint Path", "Data", reqd=1),
            _field("payload", "Payload", "Long Text", reqd=1),
            _field("payload_hash", "Payload SHA-256", "Data", reqd=1),
            _field("delivery_section", "Delivery", "Section Break"),
            _field("status", "Status", "Select", options="PENDING\nPROCESSING\nDELIVERED\nRETRY\nFAILED\nDEAD_LETTER\nCANCELLED", default="PENDING", in_list_view=1),
            _field("attempt_count", "Attempt Count", "Int", default="0"),
            _field("next_retry_at", "Next Retry At", "Datetime", in_list_view=1),
            _field("last_attempt_at", "Last Attempt At", "Datetime"),
            _field("delivered_at", "Delivered At", "Datetime"),
            _field("response_status_code", "Response Status Code", "Int"),
            _field("response_body", "Response Body", "Long Text"),
            _field("last_error", "Last Error", "Long Text"),
        ],
    )


def _ensure_custom_fields(doctype, definitions):
    for definition in definitions:
        name = f"{doctype}-{definition['fieldname']}"
        if frappe.db.exists("Custom Field", name):
            field = frappe.get_doc("Custom Field", name)
            for key, value in definition.items():
                setattr(field, key, value)
            field.save(ignore_permissions=True)
        else:
            frappe.get_doc({"doctype": "Custom Field", "name": name, "dt": doctype, **definition}).insert(ignore_permissions=True)


def _ensure_master_and_traceability_fields():
    sync_fields = [
        {"fieldname": "custom_k95_sync_status", "label": "K95 Sync Status", "fieldtype": "Select", "options": "NOT_SYNCED\nQUEUED\nSYNCED\nFAILED\nCONFLICT", "default": "NOT_SYNCED", "read_only": 1},
        {"fieldname": "custom_k95_last_synced_at", "label": "K95 Last Synced At", "fieldtype": "Datetime", "read_only": 1},
        {"fieldname": "custom_k95_last_sync_error", "label": "K95 Last Sync Error", "fieldtype": "Small Text", "read_only": 1},
    ]
    _ensure_custom_fields("Item", [
        {"fieldname": "custom_k95_item_id", "label": "K95 Item ID", "fieldtype": "Data", "unique": 1, "read_only": 1, "no_copy": 1, "in_standard_filter": 1, "insert_after": "item_name"},
        {"fieldname": "custom_k95_item_code", "label": "K95 Item Code", "fieldtype": "Data", "read_only": 1, "no_copy": 1, "insert_after": "custom_k95_item_id"},
        *sync_fields,
    ])
    _ensure_custom_fields("Supplier", [
        {"fieldname": "custom_k95_supplier_id", "label": "K95 Supplier ID", "fieldtype": "Data", "unique": 1, "read_only": 1, "no_copy": 1, "in_standard_filter": 1, "insert_after": "supplier_name"},
        {"fieldname": "custom_k95_postal_code", "label": "K95 Postal Code", "fieldtype": "Data", "insert_after": "tax_id"},
        {"fieldname": "custom_k95_approval_status", "label": "K95 Approval Status", "fieldtype": "Select", "options": "Hold\nApproved\nBlocked", "default": "Hold", "insert_after": "custom_k95_postal_code"},
        {"fieldname": "custom_publish_to_k95", "label": "Publish to K95", "fieldtype": "Check", "default": "1", "insert_after": "custom_k95_approval_status"},
        *sync_fields,
    ])
    trace_fields = [
        {"fieldname": "custom_k95_pr_id", "label": "K95 Purchase Request", "fieldtype": "Data", "read_only": 1},
        {"fieldname": "custom_k95_line_id", "label": "K95 Purchase Request Line", "fieldtype": "Data", "read_only": 1},
        {"fieldname": "custom_k95_item_id", "label": "K95 Item ID", "fieldtype": "Data", "read_only": 1},
        {"fieldname": "custom_nimr", "label": "NIMR", "fieldtype": "Link", "options": PARENT, "read_only": 1},
        {"fieldname": "custom_nimr_item_row", "label": "NIMR Item Row", "fieldtype": "Data", "read_only": 1},
    ]
    _ensure_custom_fields("Material Request Item", trace_fields)
    _ensure_custom_fields("Purchase Order Item", trace_fields)


def _ensure_item_integration_fields():
    fields = [
        {
            "fieldname": "custom_publish_to_k95",
            "label": "Publish to K95",
            "fieldtype": "Check",
            "default": "0",
            "insert_after": "custom_created_via_nimr",
        },
        {
            "fieldname": "custom_purchase_erp",
            "label": "Purchase ERP",
            "fieldtype": "Check",
            "default": "0",
            "read_only": 1,
            "insert_after": "custom_publish_to_k95",
        },
        {
            "fieldname": "custom_k95_external_pr_id",
            "label": "K95 Purchase Request",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "custom_publish_to_k95",
        },
        {
            "fieldname": "custom_k95_external_line_id",
            "label": "K95 Purchase Request Line",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "custom_k95_external_pr_id",
        },
    ]
    for definition in fields:
        name = f"Item-{definition['fieldname']}"
        if frappe.db.exists("Custom Field", name):
            continue
        frappe.get_doc(
            {
                "doctype": "Custom Field",
                "name": name,
                "dt": "Item",
                **definition,
            }
        ).insert(ignore_permissions=True)


def _extend_parent():
    _ensure_parent_fields(
        [
            _field("k95_request_section", "K95 Purchase Request", "Section Break"),
            _field("external_pr_id", "K95 Purchase Request", "Data", unique=1, read_only=1, in_list_view=1),
            _field("external_document_id", "K95 Document ID", "Data", read_only=1),
            _field("correlation_id", "Correlation ID", "Data", read_only=1),
            _field("source_event_id", "Source Event ID", "Data", read_only=1),
            _field("source_event_version", "Source Event Version", "Data", read_only=1),
            _field("source_record_version", "Source Record Version", "Int", read_only=1),
            _field("idempotency_key", "Idempotency Key", "Data", read_only=1),
            _field("source_system", "Source System", "Data", default="K95_ERP", read_only=1),
            _field("company", "Company", "Link", options="Company"),
            _field("request_title", "Request Title", "Data", read_only=1),
            _field("priority", "Priority", "Select", options="Low\nMedium\nHigh\nUrgent", read_only=1),
            _field("request_date", "Request Date", "Datetime", read_only=1),
            _field("submitted_at", "Submitted On", "Datetime", read_only=1),
            _field("requester_section", "Requester", "Section Break"),
            _field("requester_user_id", "K95 User ID", "Data", read_only=1),
            _field("requester_employee_id", "Employee ID", "Data", read_only=1),
            _field("requester_name", "Requested By", "Data", read_only=1),
            _field("requester_email", "Requester Email", "Data", options="Email", read_only=1),
            _field("department_name", "Department", "Data", read_only=1),
            _field("requested_on_behalf_of", "Requested On Behalf Of", "Data", read_only=1),
            _field("verification_section", "Approval and Store Verification", "Section Break"),
            _field("hod_status", "HOD Status", "Data", read_only=1),
            _field("hod_approved_by", "HOD Approved By", "Data", read_only=1),
            _field("hod_approved_by_email", "HOD Email", "Data", options="Email", read_only=1),
            _field("hod_approved_at", "HOD Approved On", "Datetime", read_only=1),
            _field("hod_remarks", "HOD Remarks", "Small Text", read_only=1),
            _field("store_status", "Store Verification", "Data", read_only=1),
            _field("store_verified_by", "Store Verified By", "Data", read_only=1),
            _field("store_verified_by_email", "Store Email", "Data", options="Email", read_only=1),
            _field("store_verified_at", "Store Verified On", "Datetime", read_only=1),
            _field("store_remarks", "Store Remarks", "Small Text", read_only=1),
            _field("summary_section", "Processing Summary", "Section Break"),
            _field("processing_status", "NIMR Progress", "Select", options="Pending Item Creation\nReady for MR\nPartially MR Created\nMR Fully Created\nPartially Ordered\nFully Ordered\nError", default="Pending Item Creation", read_only=1, in_list_view=1),
            _field("total_lines", "Total Lines", "Int", read_only=1),
            _field("ready_for_mr_lines", "Ready for MR", "Int", read_only=1),
            _field("pending_item_verification_lines", "Pending Item Creation", "Int", read_only=1),
            _field("mr_created_lines", "MR Created Lines", "Int", read_only=1),
            _field("ordered_lines", "Fully Ordered Lines", "Int", read_only=1),
            _field("failed_lines", "Failed", "Int", read_only=1),
            _field("items_section", "Purchase Items", "Section Break"),
            _field("items", "Purchase Items", "Table", options="NIMR Item"),
            _field("attachments_section", "Attachments", "Section Break", collapsible=1),
            _field("attachments", "Attachments", "Table", options="NIMR Item Attachment"),
            _field("allocations_section", "Material Request and Purchase Order Allocations", "Section Break", collapsible=1),
            _field("allocations", "Allocations", "Table", options="NIMR Conversion Allocation", read_only=1),
            _field("integration_section", "Integration Details", "Section Break", collapsible=1),
            _field("integration_status", "Integration Status", "Select", options="Received\nProcessing\nProcessed\nPartially Processed\nFailed", default="Received", read_only=1),
            _field("received_at", "Received On", "Datetime", read_only=1),
            _field("last_processed_at", "Last Processed On", "Datetime", read_only=1),
            _field("last_sync_at", "Last K95 Sync", "Datetime", read_only=1),
            _field("last_integration_error", "Integration Error", "Long Text", read_only=1),
            _field("source_payload_hash", "Source Payload Hash", "Data", read_only=1),
            _field("inbound_event", "Inbound Event", "Link", options="K95 Inbound Event", read_only=1),
        ]
    )


def _ensure_nimr_connections():
    doc = frappe.get_doc("DocType", PARENT)
    desired = [
        ("Item", "custom_created_via_nimr", "Purchasing"),
        ("Material Request", "custom_nimr_link", "Purchasing"),
        ("K95 Inbound Event", "nimr", "Integration"),
    ]
    existing = {(row.link_doctype, row.link_fieldname) for row in doc.links}
    changed = False
    for link_doctype, link_fieldname, group in desired:
        if (link_doctype, link_fieldname) in existing:
            continue
        doc.append(
            "links",
            {
                "link_doctype": link_doctype,
                "link_fieldname": link_fieldname,
                "group": group,
                "custom": 1,
            },
        )
        changed = True
    if changed:
        doc.save(ignore_permissions=True)


def _retire_legacy_workflow():
    """Use calculated line progress instead of the obsolete three-state workflow."""
    workflow = frappe.db.get_value(
        "Workflow", {"document_type": PARENT, "is_active": 1}, "name"
    )
    if workflow:
        frappe.db.set_value("Workflow", workflow, "is_active", 0)

    doc = frappe.get_doc("DocType", PARENT)
    status = next((row for row in doc.fields if row.fieldname == "status"), None)
    if status:
        status.label = "NIMR Progress"
        status.options = "Pending Item Creation\nReady for MR\nPartially MR Created\nMR Fully Created\nPartially Ordered\nFully Ordered\nError"
        status.default = "Pending Item Creation"
        status.read_only = 1
        doc.save(ignore_permissions=True)


def _retire_legacy_layout():
    doc = frappe.get_doc("DocType", PARENT)
    legacy_fields = {
        "section_break_kyhr",
        "amended_from",
        "item_name",
        "item_description",
        "quantity",
        "unit",
        "requested_by_date",
        "image_link",
        "email",
        "purchase_reference_section",
        "pr_unique_id",
        "pr_no",
        "system_links_and_state_section",
        "created_item",
        "created_material_request",
    }
    changed = False
    for row in doc.fields:
        if row.fieldname in legacy_fields and not row.hidden:
            row.hidden = 1
            if row.reqd:
                row.reqd = 0
            changed = True
    if changed:
        doc.save(ignore_permissions=True)

    if frappe.db.exists("Client Script", "New Item Material Request- Item"):
        frappe.db.set_value(
            "Client Script",
            "New Item Material Request- Item",
            "enabled",
            0,
            update_modified=False,
        )


def _migrate_existing_records():
    records = frappe.get_all(PARENT, pluck="name", limit_page_length=0)
    for name in records:
        doc = frappe.get_doc(PARENT, name)

        if not doc.external_pr_id:
            doc.external_pr_id = doc.pr_unique_id or doc.name
        if not doc.requester_email:
            doc.requester_email = doc.email
        if not doc.integration_status or not doc.source_event_id:
            doc.integration_status = "Processed"

        if not doc.items:
            item_status = "AUTO_MATCHED" if doc.created_item else "PENDING_ITEM_CREATION"
            processing_status = "MR_CREATED" if doc.created_material_request else (
                "READY_FOR_MR" if doc.created_item else "PENDING_ITEM_VERIFICATION"
            )
            row = doc.append(
                "items",
                {
                    "external_line_id": f"{doc.external_pr_id}-L001",
                    "line_number": 1,
                    "item_source": "MASTER" if doc.created_item else "NEW",
                    "requested_item_name": doc.item_name or "Legacy NIMR Item",
                    "requested_description": doc.item_description,
                    "requested_qty": doc.quantity or 0,
                    "purchase_required_qty": doc.quantity or 0,
                    "requested_uom": doc.unit,
                    "requested_required_by": doc.requested_by_date,
                    "erpnext_item": doc.created_item,
                    "item_resolution_status": item_status,
                    "resolution_method": "LEGACY_MIGRATION" if doc.created_item else None,
                    "final_purchase_qty": doc.quantity or 0,
                    "purchase_uom": doc.unit,
                    "conversion_factor": 1,
                    "schedule_date": doc.requested_by_date,
                    "purchase_description": doc.item_description,
                    "primary_image": doc.image_link,
                    "mr_created_qty": doc.quantity if doc.created_material_request else 0,
                    "ordered_qty": 0,
                    "pending_mr_qty": 0 if doc.created_material_request else (doc.quantity or 0),
                    "pending_order_qty": doc.quantity if doc.created_material_request else 0,
                    "processing_status": processing_status,
                },
            )

            if doc.image_link:
                doc.append(
                    "attachments",
                    {
                        "external_attachment_id": f"LEGACY-{doc.name}-IMAGE",
                        "external_line_id": row.external_line_id,
                        "media_type": "IMAGE",
                        "file_name": doc.image_link.rsplit("/", 1)[-1],
                        "file": doc.image_link,
                        "is_primary_image": 1,
                        "download_status": "DOWNLOADED",
                    },
                )

            if doc.created_material_request:
                doc.append(
                    "allocations",
                    {
                        "allocation_id": f"LEGACY-{doc.name}-A001",
                        "nimr_item_row_id": row.name,
                        "external_line_id": row.external_line_id,
                        "item_code": doc.created_item,
                        "material_request": doc.created_material_request
                        if frappe.db.exists("Material Request", doc.created_material_request)
                        else None,
                        "legacy_material_request_reference": doc.created_material_request,
                        "mr_qty": doc.quantity or 0,
                        "ordered_qty": 0,
                        "status": "MR_CREATED",
                    },
                )

        statuses = [row.processing_status for row in doc.items]
        rows_by_external_line = {row.external_line_id: row.name for row in doc.items}
        for allocation in doc.allocations:
            if not allocation.nimr_item_row_id:
                allocation.nimr_item_row_id = rows_by_external_line.get(allocation.external_line_id)
        doc.total_lines = len(doc.items)
        doc.ready_for_mr_lines = statuses.count("READY_FOR_MR")
        doc.pending_item_verification_lines = statuses.count("PENDING_ITEM_VERIFICATION")
        doc.mr_created_lines = statuses.count("MR_CREATED")
        doc.ordered_lines = statuses.count("ORDERED")
        doc.failed_lines = statuses.count("ERROR")
        if doc.ordered_lines == doc.total_lines and doc.total_lines:
            doc.processing_status = "Fully Ordered"
        elif doc.ordered_lines:
            doc.processing_status = "Partially Ordered"
        elif doc.mr_created_lines == doc.total_lines and doc.total_lines:
            doc.processing_status = "MR Fully Created"
        elif doc.mr_created_lines:
            doc.processing_status = "Partially MR Created"
        elif doc.pending_item_verification_lines:
            doc.processing_status = "Pending Item Creation"
        else:
            doc.processing_status = "Ready for MR"

        doc.status = doc.processing_status

        doc.flags.ignore_mandatory = True
        doc.flags.ignore_links = True
        doc.save(ignore_permissions=True)


def run():
    _ensure_parent_doctype()
    _create_child_doctypes()
    _create_inbound_event_doctype()
    _create_integration_settings()
    _create_outbound_event_doctype()
    _ensure_master_and_traceability_fields()
    _ensure_item_integration_fields()
    _extend_parent()
    _retire_legacy_workflow()
    _ensure_nimr_connections()
    _retire_legacy_layout()
    frappe.clear_cache(doctype=PARENT)
    _migrate_existing_records()
    frappe.db.sql(
        """update `tabNew Item Material Request`
        set status = processing_status
        where coalesce(status, '') != coalesce(processing_status, '')"""
    )
    frappe.db.commit()
    return {
        "nimr_records": frappe.db.count(PARENT),
        "child_doctypes": [
            "NIMR Item",
            "NIMR Item Attachment",
            "NIMR Conversion Allocation",
        ],
        "inbound_event_doctype": "K95 Inbound Event",
    }
