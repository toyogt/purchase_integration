frappe.ui.form.on("Purchase Integration Settings", {
    refresh(frm) {
        frm.add_custom_button(__("Test Connection"), () => {
            frappe.call({
                method: "purchase_integration.integration.test_connection",
                freeze: true,
                freeze_message: __("Testing K95 connection..."),
                callback(r) {
                    frm.reload_doc();
                    if (r.message && r.message.success) {
                        frappe.show_alert({ message: __("K95 connection succeeded"), indicator: "green" });
                    } else {
                        frappe.msgprint({ title: __("Connection failed"), indicator: "red", message: r.message?.error || __("Unknown error") });
                    }
                },
            });
        });
    },
});

frappe.ui.form.on("K95 Outbound Event", {
    refresh(frm) {
        if (["RETRY", "FAILED", "DEAD_LETTER"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Retry Delivery"), () => {
                frappe.call({
                    method: "purchase_integration.integration.retry_event",
                    args: { event_name: frm.doc.name },
                    callback() { frm.reload_doc(); },
                });
            });
        }
    },
});
