"""Isolated regressions; no site writes or outbound network calls."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from purchase_integration import events, integration, schema, hooks


class SupplierRetirementTests(unittest.TestCase):
    def test_supplier_hooks_and_endpoint_removed(self):
        self.assertNotIn("Supplier", hooks.doc_events)
        self.assertNotIn("supplier", integration.ENDPOINT_FIELDS)

    def test_old_supplier_events_never_deliver(self):
        for identity in ({"aggregate_type": "Supplier"},
                         {"event_type": "supplier.upsert"},
                         {"endpoint_path": "/api/erpnext/suppliers/upsert"}):
            with self.subTest(identity=identity):
                event = MagicMock(status="PENDING")
                event.get.side_effect = identity.get
                with patch.object(integration, "frappe") as frappe, \
                        patch.object(integration, "get_settings") as settings, \
                        patch.object(integration.requests, "post") as post:
                    frappe.db.exists.return_value = True
                    frappe.get_doc.return_value = event
                    result = integration.deliver_event("old-event")
                    self.assertEqual(result["reason"], "supplier_sync_removed")
                    self.assertEqual(event.db_set.call_args.args[0]["status"], "CANCELLED")
                    settings.assert_not_called()
                    post.assert_not_called()

    def test_non_supplier_event_still_uses_normal_delivery_path(self):
        event = MagicMock(status="PENDING")
        event.get.side_effect = {"aggregate_type": "Purchase Order"}.get
        with patch.object(integration, "frappe") as frappe, \
                patch.object(integration, "get_settings") as settings:
            frappe.db.exists.return_value = True
            frappe.get_doc.return_value = event
            settings.return_value.integration_enabled = False
            integration.deliver_event("po-event")
            event.db_set.assert_called_once_with("last_error", "Integration delivery paused")

    def test_tab_follows_standard_fields_and_keeps_legacy_types(self):
        definitions = [{"fieldname": "custom_erpk95_tab", "fieldtype": "Tab Break"},
                       {"fieldname": "custom_k95_item_id", "insert_after": "custom_erpk95_tab"}]
        with patch.object(schema, "frappe") as frappe, \
                patch.object(schema, "_ensure_custom_fields") as ensure:
            frappe.get_meta.return_value.fields = [SimpleNamespace(fieldname=name) for name in
                ("disabled", "custom_erpk95_tab", "custom_k95_item_id", "last_standard", "legacy")]
            frappe.db.exists.side_effect = lambda dt, name: name == "Item-legacy"
            schema._ensure_erpk95_fields("Item", definitions, ("legacy", "missing"))
            fields = ensure.call_args.args[1]
            self.assertEqual(fields[0]["insert_after"], "last_standard")
            self.assertEqual(fields[-1], {"fieldname": "legacy", "insert_after": "custom_k95_item_id"})
            self.assertNotIn("insert_after", definitions[0])

    def test_scoped_migration_does_not_touch_nimr(self):
        with patch.object(schema, "frappe"), \
                patch.object(schema, "_create_integration_settings") as settings, \
                patch.object(schema, "_ensure_master_and_traceability_fields") as masters, \
                patch.object(schema, "_extend_parent") as nimr, \
                patch.object(schema, "_migrate_existing_records") as records:
            schema.apply_master_integration_changes()
            settings.assert_called_once()
            masters.assert_called_once()
            nimr.assert_not_called()
            records.assert_not_called()

    def test_master_fields_remove_only_retired_supplier_fields(self):
        with patch.object(schema, "_ensure_erpk95_fields"), \
                patch.object(schema, "_remove_custom_fields") as remove, \
                patch.object(schema, "frappe"):
            schema._ensure_master_and_traceability_fields()
            remove.assert_called_once()
            doctype, fieldnames = remove.call_args.args
            self.assertEqual(doctype, "Supplier")
            self.assertIn("custom_k95_postal_code", fieldnames)
            self.assertIn("custom_k95_approval_status", fieldnames)
            self.assertIn("custom_publish_to_k95", fieldnames)
            self.assertNotIn("disabled", fieldnames)

    def test_unlinked_po_does_not_publish_supplier(self):
        doc = SimpleNamespace(items=[SimpleNamespace(custom_k95_pr_id=None, custom_nimr=None)])
        with patch.object(events, "queue_event") as queue:
            events.publish_purchase_order(doc)
            queue.assert_not_called()

    def test_linked_po_publishes_supplier_name(self):
        row = MagicMock(custom_k95_pr_id="PR-1", custom_nimr="NIMR-1")
        row.get.return_value = None
        doc = SimpleNamespace(
            items=[row], name="PO-1", modified="now", status="Draft", docstatus=0,
            supplier="SUP-1", supplier_name="Supplier One", transaction_date=None,
            schedule_date=None, currency="INR", net_total=10, grand_total=10,
            company="K95", per_received=0, per_billed=0,
        )
        with patch.object(events, "queue_event") as queue:
            events.publish_purchase_order(doc)
            payload = queue.call_args.args[3]
            self.assertEqual(payload["supplier_name"], "Supplier One")
            self.assertEqual(payload["lines"][0]["nimr"], "NIMR-1")


if __name__ == "__main__":
    unittest.main()
