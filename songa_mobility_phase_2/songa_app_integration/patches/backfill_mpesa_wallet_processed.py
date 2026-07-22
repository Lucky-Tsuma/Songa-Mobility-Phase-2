import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def ensure_mpesa_wallet_custom_fields():
	"""
	post_model_sync patches run before fixtures, so create these columns here
	when they are not yet present.
	"""
	create_custom_fields(
		{
			"Mpesa Express Request": [
				{
					"fieldname": "custom_songa_wallet_processed",
					"label": "Songa Wallet Processed",
					"fieldtype": "Check",
					"insert_after": "is_reconciled",
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
					"options": "Pending\nProcessed\nAbandoned",
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
	"""Mark historical wallet M-Pesa requests that were already handled before the processed flag existed."""
	ensure_mpesa_wallet_custom_fields()

	if not frappe.db.has_column("Mpesa Express Request", "custom_songa_wallet_processed"):
		return

	for reference_doctype, table in (
		("Rental Days", "tabRental Days"),
		("Energy KWh", "tabEnergy KWh"),
	):
		frappe.db.sql(
			f"""
			UPDATE `tabMpesa Express Request` mer
			INNER JOIN `{table}` ref ON ref.name = mer.reference_name
			SET mer.custom_songa_wallet_processed = 1,
				mer.custom_songa_wallet_process_status = 'Processed',
				mer.custom_songa_wallet_attempt_count = 0
			WHERE mer.reference_doctype = %s
			  AND mer.docstatus = 1
			  AND mer.status = 'Failed'
			  AND ref.status = 'Failed'
			  AND IFNULL(mer.custom_songa_wallet_processed, 0) = 0
			""",
			reference_doctype,
		)

	# Only reference webhook logs if that doctype table exists.
	if frappe.db.table_exists("Songa Webhook Log"):
		frappe.db.sql(
			"""
			UPDATE `tabMpesa Express Request` mer
			SET mer.custom_songa_wallet_processed = 1,
				mer.custom_songa_wallet_process_status = 'Processed',
				mer.custom_songa_wallet_attempt_count = 0
			WHERE mer.docstatus = 1
			  AND mer.status = 'Completed'
			  AND mer.reference_doctype IN ('Rental Days', 'Energy KWh')
			  AND IFNULL(mer.custom_songa_wallet_processed, 0) = 0
			  AND EXISTS (
				SELECT 1
				FROM `tabSonga Webhook Log` log
				WHERE log.reference_doctype = 'Mpesa Express Request'
				  AND log.reference_name = mer.name
				  AND log.status = 'Sent'
			  )
			"""
		)

	# Default remaining wallet STK rows to Pending so the capped cron can pick them up.
	frappe.db.sql(
		"""
		UPDATE `tabMpesa Express Request` mer
		SET mer.custom_songa_wallet_process_status = 'Pending',
			mer.custom_songa_wallet_attempt_count = IFNULL(mer.custom_songa_wallet_attempt_count, 0)
		WHERE mer.docstatus = 1
		  AND mer.reference_doctype IN ('Rental Days', 'Energy KWh')
		  AND IFNULL(mer.custom_songa_wallet_processed, 0) = 0
		  AND IFNULL(mer.custom_songa_wallet_process_status, '') IN ('', 'Pending')
		"""
	)
