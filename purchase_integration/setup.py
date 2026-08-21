from purchase_integration import layout, schema


def migrate():
	"""Install or update the NIMR integration schema and form layout."""
	schema.run()
	layout.run()


def after_install():
	migrate()


def after_migrate():
	migrate()
