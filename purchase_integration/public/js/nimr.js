frappe.provide("purchase_integration.nimr");

purchase_integration.nimr.paint_item_rows = function (frm) {
	if (!document.getElementById("nimr-row-status-styles")) {
		$("<style>", {
			id: "nimr-row-status-styles",
			text: `
				.nimr-row-pending .grid-static-col { background-color:#fff7df !important; }
				.nimr-row-ready .grid-static-col { background-color:#eef6ff !important; }
				.nimr-row-mr-created .grid-static-col { background-color:#ecfdf3 !important; }
				.nimr-row-ordered .grid-static-col { background-color:#f5f3ff !important; }
				.nimr-row-error .grid-static-col { background-color:#fff1f2 !important; }
			`,
		}).appendTo("head");
	}
	const progress_colors = {
		"Pending Item Creation": "orange",
		"Ready for MR": "blue",
		"Partially MR Created": "orange",
		"MR Fully Created": "green",
		"Partially Ordered": "purple",
		"Fully Ordered": "green",
		Error: "red",
	};
	frm.set_intro(
		__("NIMR Progress: {0}", [frm.doc.processing_status || "Pending Item Creation"]),
		progress_colors[frm.doc.processing_status] || "blue"
	);

	setTimeout(() => {
		const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
		if (!grid) return;
		const palette = {
			PENDING_ITEM_VERIFICATION: { className: "nimr-row-pending", border: "#f59e0b" },
			READY_FOR_MR: { className: "nimr-row-ready", border: "#3b82f6" },
			PARTIALLY_CONVERTED: { className: "nimr-row-pending", border: "#f59e0b" },
			MR_CREATED: { className: "nimr-row-mr-created", border: "#22c55e" },
			PARTIALLY_ORDERED: { className: "nimr-row-ordered", border: "#8b5cf6" },
			ORDERED: { className: "nimr-row-ordered", border: "#15803d" },
			ERROR: { className: "nimr-row-error", border: "#ef4444" },
		};
		grid.grid_rows.forEach((grid_row) => {
			const style = palette[grid_row.doc.processing_status] || palette.PENDING_ITEM_VERIFICATION;
			const $row = grid_row.wrapper || grid_row.row;
			$row.removeClass("nimr-row-pending nimr-row-ready nimr-row-mr-created nimr-row-ordered nimr-row-error");
			$row.addClass(style.className).css("border-left", `5px solid ${style.border}`);
		});
	}, 0);
};

purchase_integration.nimr.open_create_item_dialog = function (frm, row) {
	const suggested_code = `K95-${(row.requested_item_name || "NEW-ITEM")
		.toUpperCase()
		.replace(/[^A-Z0-9]+/g, "-")
		.replace(/^-|-$/g, "")
		.slice(0, 100)}`;
	const image = row.primary_image
		? `<div style="margin-bottom:12px"><img src="${frappe.utils.escape_html(row.primary_image)}" alt="Reference image" style="max-width:220px;max-height:160px;border:1px solid var(--border-color);border-radius:8px;padding:4px"></div>`
		: `<div class="text-muted">${__("No reference image was supplied.")}</div>`;

	const dialog = new frappe.ui.Dialog({
		title: __("Create Item from NIMR Line {0}", [row.line_number || row.idx]),
		fields: [
			{ fieldname: "reference_image", fieldtype: "HTML", options: image },
			{ fieldname: "item_code", label: __("Item Code"), fieldtype: "Data", reqd: 1, default: suggested_code },
			{ fieldname: "item_name", label: __("Item Name"), fieldtype: "Data", reqd: 1, default: row.requested_item_name },
			{ fieldname: "column_break_1", fieldtype: "Column Break" },
			{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group", reqd: 1 },
			{ fieldname: "stock_uom", label: __("Stock UOM"), fieldtype: "Link", options: "UOM", reqd: 1, default: row.purchase_uom || row.requested_uom },
			{ fieldname: "gst_hsn_code", label: __("HSN/SAC"), fieldtype: "Link", options: "GST HSN Code", reqd: 1 },
			{ fieldname: "details_section", label: __("Details"), fieldtype: "Section Break" },
			{ fieldname: "description", label: __("Description"), fieldtype: "Small Text", default: row.purchase_description || row.requested_description },
			{ fieldname: "is_stock_item", label: __("Maintain Stock"), fieldtype: "Check", default: 1 },
			{ fieldname: "publish_to_k95", label: __("Publish this Item to K95"), fieldtype: "Check", default: row.publish_item_to_k95 ? 1 : 0 },
		],
		primary_action_label: __("Create Item"),
		primary_action(values) {
			dialog.disable_primary_action();
			frappe.call({
				method: "purchase_integration.nimr.create_item_from_nimr",
				args: {
					nimr_name: frm.doc.name,
					row_name: row.name,
					values,
				},
				freeze: true,
				freeze_message: __("Creating Item..."),
			}).then((response) => {
				const result = response.message;
				if (!result) return;
				dialog.hide();
				frm.reload_doc();
				const item_link = frappe.utils.get_form_link("Item", result.item_code, true);
				frappe.msgprint({
					title: result.created ? __("Item Created") : __("Item Already Linked"),
					indicator: "green",
					message: `${result.created ? __("Item created successfully") : __("This line is already linked")}: ${item_link}`,
				});
			}).catch(() => dialog.enable_primary_action());
		},
	});

	dialog.show();
};

frappe.ui.form.on("New Item Material Request", {
	refresh(frm) {
		if (frm.is_new()) return;
		purchase_integration.nimr.paint_item_rows(frm);
		const unresolved = (frm.doc.items || []).filter((row) => !row.erpnext_item);
		if (unresolved.length && !frm.is_dirty() && !frm.__nimr_auto_match_checked) {
			frm.__nimr_auto_match_checked = true;
			frappe.call({
				method: "purchase_integration.nimr.auto_match_existing_items",
				args: { nimr_name: frm.doc.name },
			}).then((response) => {
				const result = response.message;
				if (result && result.count) {
					frappe.show_alert({
						message: __("Automatically matched {0} existing Item(s).", [result.count]),
						indicator: "green",
					});
					frm.reload_doc();
				}
			});
		}
		frm.add_custom_button(__("Create Item"), () => {
			const selected = frm.fields_dict.items.grid
				.get_selected_children()
				.filter((row) => !row.erpnext_item);
			if (selected.length === 1) {
				purchase_integration.nimr.open_create_item_dialog(frm, selected[0]);
				return;
			}
			if (selected.length > 1) {
				frappe.msgprint(__("Select only one unresolved item row for Item creation."));
				return;
			}
			if (unresolved.length === 1) {
				purchase_integration.nimr.open_create_item_dialog(frm, unresolved[0]);
				return;
			}
			frappe.msgprint(__("Select one pending item using the checkbox, then click Create Item."));
		});

		frm.add_custom_button(__("Create MR by Choosing Item"), () => {
			const selected = frm.fields_dict.items.grid.get_selected_children();
			if (!selected.length) {
				frappe.msgprint(__("Select one or more eligible item rows using the checkboxes first."));
				return;
			}
			frappe.call({
				method: "purchase_integration.nimr.create_material_request",
				args: {
					nimr_name: frm.doc.name,
					row_names: selected.map((row) => row.name),
				},
				freeze: true,
				freeze_message: __("Creating Material Request..."),
			}).then((response) => {
				const result = response.message;
				if (!result) return;
				frm.reload_doc();
				frappe.msgprint({
					title: __("Material Request Created"),
					indicator: "green",
					message: __("Material Request {0} was created with {1} item(s).", [
						frappe.utils.get_form_link("Material Request", result.material_request, true),
						result.items,
					]),
				});
			});
		});
	},
});

frappe.ui.form.on("NIMR Item", {
	form_render(frm) {
		purchase_integration.nimr.paint_item_rows(frm);
	},
	create_item_action(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.erpnext_item) {
			frappe.show_alert({ message: __("Item {0} is already linked.", [row.erpnext_item]), indicator: "blue" });
			return;
		}
		purchase_integration.nimr.open_create_item_dialog(frm, row);
	},
});
