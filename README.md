# Purchase Integration

ERPNext/Frappe v15 application for the K95 Purchase Request → NIMR → Material Request → Purchase Order integration.

## Automatic provisioning

The `after_install` and `after_migrate` hooks run an idempotent schema installer. A fresh installation and every later `bench migrate` create or update:

- New Item Material Request and its clean tabbed layout
- NIMR Item, Attachment, and Conversion Allocation child DocTypes
- Purchase Integration Settings
- K95 Inbound Event and K95 Outbound Event
- Item and Supplier K95 identity and sync fields
- Material Request Item and Purchase Order Item traceability fields
- NIMR Connections
- calculated progress states and retirement of the obsolete legacy Workflow
- legacy NIMR record migration

No manual Customize Form export is required.

## Installation

```bash
cd /home/frappe/frappe-bench
bench get-app https://YOUR_GIT_SERVER/YOUR_ORG/purchase_integration.git --branch main
bench --site YOUR_SITE install-app purchase_integration
bench --site YOUR_SITE migrate
bench build --app purchase_integration
bench restart
```

For upgrades:

```bash
cd /home/frappe/frappe-bench/apps/purchase_integration
git pull
cd ../..
bench --site YOUR_SITE migrate
bench build --app purchase_integration
bench restart
```

## Inbound endpoint

```text
POST /api/method/purchase_integration.api.receive_purchase_request
```

Only `Purchase Required` lines with `send_to_erpnext: true` are imported. The receiver is HMAC authenticated and idempotent.

## Configuration

Open **Purchase Integration Settings**, enter the company, public URLs, K95 endpoint paths, authentication credentials and retry policy. Run **Test Connection** before enabling integration.

Do not commit secrets. Password fields are encrypted in the ERPNext site database.

## Verification

```bash
bench --site YOUR_SITE execute purchase_integration.qa.dry_test
```

The result must contain `"passed": true`.

## Compatibility

- Frappe Framework v15
- ERPNext v15
- Python 3.10+

## License

MIT
