import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def ensure_mpesa_c2b_wallet_custom_fields():
	"""
	post_model_sync patches run before fixtures, so create these columns here
	when they are not yet present.
	"""
	create_custom_fields(
		{
			"Mpesa C2B Payment Register": [
				{
					"fieldname": "custom_songa_wallet_section",
					"label": "Songa Wallet",
					"fieldtype": "Section Break",
					"insert_after": "submit_payment",
					"collapsible": 1,
					"module": "Songa App Integration",
				},
				{
					"fieldname": "custom_songa_reference_doctype",
					"label": "Songa Reference Doctype",
					"fieldtype": "Link",
					"options": "DocType",
					"insert_after": "custom_songa_wallet_section",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"module": "Songa App Integration",
				},
				{
					"fieldname": "custom_songa_reference_name",
					"label": "Songa Reference Name",
					"fieldtype": "Dynamic Link",
					"options": "custom_songa_reference_doctype",
					"insert_after": "custom_songa_reference_doctype",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"module": "Songa App Integration",
				},
				{
					"fieldname": "custom_songa_wallet_processed",
					"label": "Songa Wallet Processed",
					"fieldtype": "Check",
					"insert_after": "custom_songa_reference_name",
					"default": "0",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"module": "Songa App Integration",
				},
				{
					"fieldname": "custom_songa_wallet_attempt_count",
					"label": "Songa Wallet Attempt Count",
					"fieldtype": "Int",
					"insert_after": "custom_songa_wallet_processed",
					"default": "0",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"non_negative": 1,
					"module": "Songa App Integration",
				},
				{
					"fieldname": "custom_songa_wallet_last_attempt_on",
					"label": "Songa Wallet Last Attempt On",
					"fieldtype": "Datetime",
					"insert_after": "custom_songa_wallet_attempt_count",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"module": "Songa App Integration",
				},
				{
					"fieldname": "custom_songa_wallet_process_status",
					"label": "Songa Wallet Process Status",
					"fieldtype": "Select",
					"options": "Pending\nProcessed",
					"insert_after": "custom_songa_wallet_last_attempt_on",
					"default": "Pending",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"module": "Songa App Integration",
				},
				{
					"fieldname": "custom_songa_journal_entry",
					"label": "Songa Journal Entry",
					"fieldtype": "Link",
					"options": "Journal Entry",
					"insert_after": "custom_songa_wallet_process_status",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"module": "Songa App Integration",
				},
			]
		},
		ignore_validate=True,
		update=True,
	)


def execute():
	ensure_mpesa_c2b_wallet_custom_fields()
