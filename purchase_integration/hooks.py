app_name = "purchase_integration"
app_title = "Purchase Integration"
app_publisher = "K95 Foods Private Limited"
app_description = "K95 purchase request and procurement integration"
app_email = "erpnextapi@gmail.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "purchase_integration",
# 		"logo": "/assets/purchase_integration/logo.png",
# 		"title": "Purchase Integration",
# 		"route": "/purchase_integration",
# 		"has_permission": "purchase_integration.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/purchase_integration/css/purchase_integration.css"
app_include_js = [
	"/assets/purchase_integration/js/nimr.js",
	"/assets/purchase_integration/js/integration.js",
]

doc_events = {
	"New Item Material Request": {
		"before_validate": "purchase_integration.nimr.auto_match_on_validate",
		"on_submit": "purchase_integration.nimr.create_mr_on_submit",
	},
	"Item": {
		"on_update": "purchase_integration.events.publish_item",
	},
	"Supplier": {
		"validate": "purchase_integration.events.validate_supplier",
		"on_update": "purchase_integration.events.publish_supplier",
	},
	"Material Request": {
		"on_update": "purchase_integration.events.publish_material_request",
		"on_cancel": "purchase_integration.events.publish_material_request",
	},
	"Purchase Order": {
		"validate": "purchase_integration.events.propagate_po_traceability",
		"on_update": "purchase_integration.events.publish_purchase_order",
		"on_cancel": "purchase_integration.events.publish_purchase_order",
	},
}

scheduler_events = {
	"cron": {
		"* * * * *": ["purchase_integration.tasks.process_outbound_events"],
	}
}

# include js, css files in header of web template
# web_include_css = "/assets/purchase_integration/css/purchase_integration.css"
# web_include_js = "/assets/purchase_integration/js/purchase_integration.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "purchase_integration/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# NIMR is a custom DocType, so its controller is included in Desk explicitly.
# This avoids custom-DocType controller caching preventing child-row button events.
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "purchase_integration/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "purchase_integration.utils.jinja_methods",
# 	"filters": "purchase_integration.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "purchase_integration.install.before_install"
after_install = "purchase_integration.setup.after_install"
after_migrate = "purchase_integration.setup.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "purchase_integration.uninstall.before_uninstall"
# after_uninstall = "purchase_integration.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "purchase_integration.utils.before_app_install"
# after_app_install = "purchase_integration.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "purchase_integration.utils.before_app_uninstall"
# after_app_uninstall = "purchase_integration.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "purchase_integration.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"purchase_integration.tasks.all"
# 	],
# 	"daily": [
# 		"purchase_integration.tasks.daily"
# 	],
# 	"hourly": [
# 		"purchase_integration.tasks.hourly"
# 	],
# 	"weekly": [
# 		"purchase_integration.tasks.weekly"
# 	],
# 	"monthly": [
# 		"purchase_integration.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "purchase_integration.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "purchase_integration.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "purchase_integration.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["purchase_integration.utils.before_request"]
# after_request = ["purchase_integration.utils.after_request"]

# Job Events
# ----------
# before_job = ["purchase_integration.utils.before_job"]
# after_job = ["purchase_integration.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"purchase_integration.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
