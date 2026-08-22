import frappe
from frappe import _
from frappe.utils import now_datetime


def _find_line(nimr, row_name):
	for row in nimr.items:
		if row.name == row_name:
			return row
	frappe.throw(_("NIMR Item row {0} was not found.").format(row_name))


def _update_summary(nimr):
	statuses = [row.processing_status for row in nimr.items]
	actionable = [row for row in nimr.items if (row.final_purchase_qty or 0) > 0]
	fully_converted = [
		row for row in actionable if (row.mr_created_qty or 0) >= (row.final_purchase_qty or 0)
	]
	partly_converted = [row for row in actionable if (row.mr_created_qty or 0) > 0]
	fully_ordered = [
		row for row in actionable if (row.ordered_qty or 0) >= (row.final_purchase_qty or 0)
	]
	partly_ordered = [row for row in actionable if (row.ordered_qty or 0) > 0]
	nimr.total_lines = len(nimr.items)
	nimr.ready_for_mr_lines = sum(
		1 for row in actionable if row.erpnext_item and (row.pending_mr_qty or 0) > 0
	)
	nimr.pending_item_verification_lines = sum(1 for row in actionable if not row.erpnext_item)
	nimr.mr_created_lines = len(fully_converted)
	nimr.ordered_lines = len(fully_ordered)
	nimr.failed_lines = statuses.count("ERROR")

	if actionable and len(fully_ordered) == len(actionable):
		nimr.processing_status = "Fully Ordered"
	elif partly_ordered:
		nimr.processing_status = "Partially Ordered"
	elif actionable and len(fully_converted) == len(actionable):
		nimr.processing_status = "MR Fully Created"
	elif partly_converted:
		nimr.processing_status = "Partially MR Created"
	elif nimr.pending_item_verification_lines:
		nimr.processing_status = "Pending Item Creation"
	else:
		nimr.processing_status = "Ready for MR"


def _set_parent_summary(nimr, extra_values=None):
	_update_summary(nimr)
	values = {
		"total_lines": nimr.total_lines,
		"ready_for_mr_lines": nimr.ready_for_mr_lines,
		"pending_item_verification_lines": nimr.pending_item_verification_lines,
		"mr_created_lines": nimr.mr_created_lines,
		"ordered_lines": nimr.ordered_lines,
		"failed_lines": nimr.failed_lines,
		"processing_status": nimr.processing_status,
		"status": nimr.processing_status,
	}
	values.update(extra_values or {})
	frappe.db.set_value("New Item Material Request", nimr.name, values)


def _find_unique_existing_item(row):
	if row.k95_item_id:
		mapped = frappe.db.get_value(
			"Item", {"custom_k95_item_id": row.k95_item_id, "disabled": 0}, "name"
		)
		if mapped:
			return mapped, "K95_ITEM_ID"
	return None, None


def _auto_match_doc(nimr):
	matched = []
	for row in nimr.items:
		if row.erpnext_item:
			item = frappe.db.get_value(
				"Item", {"name": row.erpnext_item, "disabled": 0}, ["stock_uom", "item_name"], as_dict=True
			)
			if not item:
				row.erpnext_item = None
				row.item_resolution_status = "PENDING_ITEM_CREATION"
				row.processing_status = "PENDING_ITEM_VERIFICATION"
				continue
			row.purchase_uom = item.stock_uom
			row.item_resolution_status = row.item_resolution_status or "MANUALLY_MATCHED"
			row.processing_status = "READY_FOR_MR"
			row.pending_mr_qty = max(
				(row.final_purchase_qty or 0) - (row.mr_created_qty or 0), 0
			)
			continue
		item_code, method = _find_unique_existing_item(row)
		if not item_code:
			continue
		item = frappe.db.get_value(
			"Item", item_code, ["stock_uom", "item_name"], as_dict=True
		)
		row.erpnext_item = item_code
		row.item_resolution_status = "AUTO_MATCHED"
		row.resolution_method = method
		row.processing_status = "READY_FOR_MR"
		row.resolved_by = frappe.session.user
		row.resolved_at = now_datetime()
		row.purchase_uom = item.stock_uom
		if not row.final_purchase_qty:
			row.final_purchase_qty = row.purchase_required_qty
		row.pending_mr_qty = max(
			(row.final_purchase_qty or 0) - (row.mr_created_qty or 0), 0
		)
		matched.append({"row": row.name, "item_code": item_code, "method": method})
	_update_summary(nimr)
	nimr.status = nimr.processing_status
	return matched


def auto_match_on_validate(doc, method=None):
	_auto_match_doc(doc)


@frappe.whitelist()
def auto_match_existing_items(nimr_name):
	nimr = frappe.get_doc("New Item Material Request", nimr_name)
	nimr.check_permission("write")
	matched = _auto_match_doc(nimr)
	if matched:
		nimr.save()
	return {"matched": matched, "count": len(matched), "progress": nimr.processing_status}


@frappe.whitelist()
def create_item_from_nimr(nimr_name, row_name, values):
	"""Create one Item from an unresolved NIMR child row and link it atomically."""
	if isinstance(values, str):
		values = frappe.parse_json(values)

	nimr = frappe.get_doc("New Item Material Request", nimr_name)
	nimr.check_permission("write")
	frappe.has_permission("Item", ptype="create", throw=True)
	row = _find_line(nimr, row_name)
	locked_item = frappe.db.sql(
		"select erpnext_item from `tabNIMR Item` where name=%s for update",
		row.name,
		as_dict=True,
	)[0].erpnext_item
	if locked_item:
		return {
			"created": False,
			"item_code": locked_item,
			"item_name": frappe.db.get_value("Item", locked_item, "item_name"),
			"message": _("This NIMR line is already linked to Item {0}.").format(locked_item),
		}

	item_code = (values.get("item_code") or "").strip()
	item_name = (values.get("item_name") or row.requested_item_name or "").strip()
	item_group = values.get("item_group")
	stock_uom = values.get("stock_uom")
	hsn_code = values.get("gst_hsn_code")

	if not item_code or not item_name or not item_group or not stock_uom:
		frappe.throw(_("Item Code, Item Name, Item Group, and Stock UOM are required."))
	if frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} already exists. Use Match Existing Item instead.").format(item_code))
	if not frappe.db.exists("Item Group", item_group):
		frappe.throw(_("Item Group {0} does not exist.").format(item_group))
	if not frappe.db.exists("UOM", stock_uom):
		frappe.throw(_("UOM {0} does not exist.").format(stock_uom))
	item_meta = frappe.get_meta("Item")
	if item_meta.has_field("gst_hsn_code"):
		if not hsn_code:
			frappe.throw(_("HSN/SAC is required for Items created from NIMR."))
		if not frappe.db.exists("GST HSN Code", hsn_code):
			frappe.throw(_("HSN/SAC {0} does not exist.").format(hsn_code))

	existing_same_name = frappe.db.get_value(
		"Item", {"item_name": item_name, "disabled": 0}, "name"
	)
	if existing_same_name:
		frappe.throw(
			_("An enabled Item with the same name already exists: {0}. Review and match it instead.").format(
				existing_same_name
			)
		)

	item_values = {
		"doctype": "Item",
		"item_code": item_code,
		"item_name": item_name,
		"description": values.get("description") or row.purchase_description or row.requested_description,
		"item_group": item_group,
		"stock_uom": stock_uom,
		"is_stock_item": int(values.get("is_stock_item") or 0),
		"is_purchase_item": 1,
		"image": row.primary_image,
	}
	if item_meta.has_field("gst_hsn_code"):
		item_values["gst_hsn_code"] = hsn_code
	optional_values = {
		"custom_k95_item_id": row.k95_item_id,
		"custom_k95_item_code": row.external_item_code,
		"custom_created_via_nimr": nimr.name,
		"custom_proposed_item_name": row.requested_item_name,
		"custom_item_description_": row.requested_description,
		"custom_quantity": row.purchase_required_qty,
		"custom_unit": row.requested_uom,
		"custom_requested_by_date": row.requested_required_by,
		"custom_gmail": nimr.requester_email,
		"custom_image_link": row.primary_image,
		"custom_pr_unique_id": nimr.external_pr_id,
		"custom_pr_no": nimr.external_pr_id,
		"custom_publish_to_k95": int(values.get("publish_to_k95") or 0),
		"custom_purchase_erp": 1,
		"custom_k95_external_pr_id": nimr.external_pr_id,
		"custom_k95_external_line_id": row.external_line_id,
	}
	for fieldname, value in optional_values.items():
		if item_meta.has_field(fieldname):
			item_values[fieldname] = value

	item = frappe.get_doc(item_values)
	item.insert()

	row.erpnext_item = item.name
	row.item_resolution_status = "NEW_ITEM_CREATED"
	row.resolution_method = "CREATED_FROM_NIMR"
	row.processing_status = "READY_FOR_MR"
	row.resolved_by = frappe.session.user
	row.resolved_at = now_datetime()
	row.purchase_uom = stock_uom
	if not row.final_purchase_qty:
		row.final_purchase_qty = row.purchase_required_qty
	row.pending_mr_qty = max((row.final_purchase_qty or 0) - (row.mr_created_qty or 0), 0)

	_update_summary(nimr)
	# Do not save the complete parent here. Older NIMR automations may update the
	# workflow state when an Item is inserted, and a full save can then attempt an
	# invalid backward transition (for example MR Created -> Item Created).
	frappe.db.set_value(
		"NIMR Item",
		row.name,
		{
			"erpnext_item": row.erpnext_item,
			"item_resolution_status": row.item_resolution_status,
			"resolution_method": row.resolution_method,
			"processing_status": row.processing_status,
			"resolved_by": row.resolved_by,
			"resolved_at": row.resolved_at,
			"purchase_uom": row.purchase_uom,
			"final_purchase_qty": row.final_purchase_qty,
			"pending_mr_qty": row.pending_mr_qty,
		},
		update_modified=False,
	)
	frappe.db.set_value(
		"New Item Material Request",
		nimr.name,
		{
			"status": nimr.processing_status,
			"total_lines": nimr.total_lines,
			"ready_for_mr_lines": nimr.ready_for_mr_lines,
			"pending_item_verification_lines": nimr.pending_item_verification_lines,
			"mr_created_lines": nimr.mr_created_lines,
			"ordered_lines": nimr.ordered_lines,
			"failed_lines": nimr.failed_lines,
			"processing_status": nimr.processing_status,
		},
	)

	return {
		"created": True,
		"item_code": item.name,
		"item_name": item.item_name,
		"nimr": nimr.name,
		"row_name": row.name,
		"processing_status": row.processing_status,
	}


@frappe.whitelist()
def create_material_request(nimr_name, row_names=None):
	"""Create one draft Purchase Material Request from selected eligible NIMR lines."""
	if isinstance(row_names, str):
		row_names = frappe.parse_json(row_names)
	row_names = set(row_names or [])

	nimr = frappe.get_doc("New Item Material Request", nimr_name)
	nimr.check_permission("write")
	frappe.has_permission("Material Request", ptype="create", throw=True)
	if row_names:
		placeholders = ", ".join(["%s"] * len(row_names))
		frappe.db.sql(
			f"select name from `tabNIMR Item` where name in ({placeholders}) for update",
			tuple(row_names),
		)
		nimr = frappe.get_doc("New Item Material Request", nimr_name)

	selected = [row for row in nimr.items if not row_names or row.name in row_names]
	if row_names and len(selected) != len(row_names):
		frappe.throw(_("One or more selected NIMR lines were not found."))

	eligible = []
	for row in selected:
		pending_qty = max((row.final_purchase_qty or 0) - (row.mr_created_qty or 0), 0)
		if not row.erpnext_item:
			frappe.throw(_("Create or match an ERPNext Item for line {0} first.").format(row.line_number or row.idx))
		if pending_qty <= 0:
			continue
		if not row.schedule_date:
			frappe.throw(_("Required By is missing for line {0}.").format(row.line_number or row.idx))
		conversion_key = f"{nimr.name}|{row.name}|{pending_qty:.6f}|{row.schedule_date}"
		if frappe.db.exists("NIMR Conversion Allocation", {"conversion_key": conversion_key}):
			frappe.throw(_("An MR was already created for line {0} with the same quantity and date.").format(row.line_number or row.idx))
		eligible.append((row, pending_qty))

	if not eligible:
		frappe.throw(_("The selected lines have no quantity pending for Material Request."))

	mr_values = {
		"doctype": "Material Request",
		"material_request_type": "Purchase",
		"company": nimr.company,
		"items": [],
	}
	if frappe.get_meta("Material Request").has_field("custom_nimr_link"):
		mr_values["custom_nimr_link"] = nimr.name

	for row, pending_qty in eligible:
		mr_values["items"].append(
			{
				"item_code": row.erpnext_item,
				"qty": pending_qty,
				"schedule_date": row.schedule_date,
				"warehouse": row.target_warehouse,
				"description": row.purchase_description or row.requested_description,
				"custom_k95_pr_id": nimr.external_pr_id,
				"custom_k95_line_id": row.external_line_id,
				"custom_k95_item_id": row.k95_item_id or frappe.db.get_value("Item", row.erpnext_item, "custom_k95_item_id"),
				"custom_nimr": nimr.name,
				"custom_nimr_item_row": row.name,
			}
		)

	mr = frappe.get_doc(mr_values).insert()
	allocation_idx = frappe.db.count("NIMR Conversion Allocation", {"parent": nimr.name})
	for (row, pending_qty), mr_item in zip(eligible, mr.items):
		new_mr_qty = (row.mr_created_qty or 0) + pending_qty
		frappe.db.set_value(
			"NIMR Item",
			row.name,
			{
				"mr_created_qty": new_mr_qty,
				"pending_mr_qty": 0,
				"processing_status": "MR_CREATED",
			},
			update_modified=False,
		)
		row.mr_created_qty = new_mr_qty
		row.pending_mr_qty = 0
		row.processing_status = "MR_CREATED"
		allocation_idx += 1
		frappe.get_doc(
			{
				"doctype": "NIMR Conversion Allocation",
				"parent": nimr.name,
				"parenttype": "New Item Material Request",
				"parentfield": "allocations",
				"idx": allocation_idx,
				"allocation_id": f"{nimr.name}:{row.external_line_id}:{mr.name}",
				"nimr_item_row_id": row.name,
				"external_line_id": row.external_line_id,
				"item_code": row.erpnext_item,
				"material_request": mr.name,
				"material_request_item_id": mr_item.name,
				"mr_qty": pending_qty,
				"schedule_date": row.schedule_date,
				"conversion_key": f"{nimr.name}|{row.name}|{pending_qty:.6f}|{row.schedule_date}",
				"status": "MR_CREATED",
			}
		).db_insert()

	_set_parent_summary(nimr, {"created_material_request": mr.name})
	return {
		"material_request": mr.name,
		"items": len(mr.items),
		"total_qty": sum(qty for _row, qty in eligible),
		"route": f"/app/material-request/{mr.name}",
	}


def create_mr_on_submit(doc, method=None):
	eligible_rows = [
		row.name
		for row in doc.items
		if row.erpnext_item and max((row.final_purchase_qty or 0) - (row.mr_created_qty or 0), 0) > 0
	]
	if eligible_rows:
		create_material_request(doc.name, eligible_rows)


def create_mr_on_workflow_completion(doc, method=None):
	"""Treat the current workflow's final MR Created state as submission."""
	if doc.status == "MR Created":
		create_mr_on_submit(doc, method)
