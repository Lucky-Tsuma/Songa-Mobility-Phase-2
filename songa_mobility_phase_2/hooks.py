app_name = "songa_mobility_phase_2"
app_title = "Songa Mobility Phase 2"
app_publisher = "Lucky Tsuma"
app_description = "Customizations for the second phase of Songa Mobility project"
app_email = "tsuma@teamweb.africa"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "songa_mobility_phase_2",
# 		"logo": "/assets/songa_mobility_phase_2/logo.png",
# 		"title": "Songa Mobility Phase 2",
# 		"route": "/songa_mobility_phase_2",
# 		"has_permission": "songa_mobility_phase_2.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/songa_mobility_phase_2/css/songa_mobility_phase_2.css"
app_include_js = ["/assets/songa_mobility_phase_2/js/driver.js"]

# include js, css files in header of web template
# web_include_css = "/assets/songa_mobility_phase_2/css/songa_mobility_phase_2.css"
# web_include_js = "/assets/songa_mobility_phase_2/js/songa_mobility_phase_2.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "songa_mobility_phase_2/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "songa_mobility_phase_2/public/icons.svg"

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
# 	"methods": "songa_mobility_phase_2.utils.jinja_methods",
# 	"filters": "songa_mobility_phase_2.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "songa_mobility_phase_2.install.before_install"
# after_install = "songa_mobility_phase_2.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "songa_mobility_phase_2.uninstall.before_uninstall"
# after_uninstall = "songa_mobility_phase_2.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "songa_mobility_phase_2.utils.before_app_install"
# after_app_install = "songa_mobility_phase_2.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "songa_mobility_phase_2.utils.before_app_uninstall"
# after_app_uninstall = "songa_mobility_phase_2.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "songa_mobility_phase_2.notifications.get_notification_config"

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

doc_events = {
	"Driver Commission Ledger": {
		"on_update": "songa_mobility_phase_2.services.workflow_handlers.handle_commission_ledger_workflow.handle_commission_ledger_workflow"
	},
	"Comment": {
		"on_update": "songa_mobility_phase_2.songa_app_integration.events.events.on_comment_update",
	},
	"Asset Repair": {
		"on_update": "songa_mobility_phase_2.songa_app_integration.events.events.on_asset_repair_update",
	},
	"Driver": {
		"after_insert": "songa_mobility_phase_2.songa_app_integration.events.events.on_driver_insert",
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"* * * * *": [
			"songa_mobility_phase_2.songa_app_integration.utils.tasks.process_pending_mpesa_express_requests"
		]
	}
	# 	"all": [
	# 		"songa_mobility_phase_2.tasks.all"
	# 	],
	# 	"daily": [
	# 		"songa_mobility_phase_2.tasks.daily"
	# 	],
	# 	"hourly": [
	# 		"songa_mobility_phase_2.tasks.hourly"
	# 	],
	# 	"weekly": [
	# 		"songa_mobility_phase_2.tasks.weekly"
	# 	],
	# 	"monthly": [
	# 		"songa_mobility_phase_2.tasks.monthly"
	# 	],
}

# Testing
# -------

# before_tests = "songa_mobility_phase_2.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "songa_mobility_phase_2.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "songa_mobility_phase_2.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["songa_mobility_phase_2.utils.before_request"]
# after_request = ["songa_mobility_phase_2.utils.after_request"]

# Job Events
# ----------
# before_job = ["songa_mobility_phase_2.utils.before_job"]
# after_job = ["songa_mobility_phase_2.utils.after_job"]

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
# 	"songa_mobility_phase_2.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

fixtures = [
	{
		"dt": "Custom Field",
		"filters": {"module": ["in", ["Songa App Integration", "Songa Mobility Phase 2"]]},
	},
	{"dt": "Workflow", "filters": {"document_type": ["in", ["Driver Commission Ledger"]]}},
	{"dt": "Role", "filters": {"name": ["in", ["Songa App", "Commission Ledger Approver"]]}},
	{"dt": "Notification", "filters": {"document_type": ["in", ["Asset Repair"]]}},
	"Workflow State",
	"Workflow Action Master",
	"Custom DocPerm",
	"Asset Type",
	"Severity Type",
]
