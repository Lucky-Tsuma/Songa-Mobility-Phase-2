import frappe


def execute():
	"""Mark historical wallet M-Pesa requests that were already handled before the processed flag existed."""
	for reference_doctype, table in (
		("Rental Days", "tabRental Days"),
		("Energy KWh", "tabEnergy KWh"),
	):
		frappe.db.sql(
			f"""
			UPDATE `tabMpesa Express Request` mer
			INNER JOIN `{table}` ref ON ref.name = mer.reference_name
			SET mer.custom_songa_wallet_processed = 1
			WHERE mer.reference_doctype = %s
			  AND mer.docstatus = 1
			  AND mer.status = 'Failed'
			  AND ref.status = 'Failed'
			  AND IFNULL(mer.custom_songa_wallet_processed, 0) = 0
			""",
			reference_doctype,
		)

	frappe.db.sql(
		"""
		UPDATE `tabMpesa Express Request` mer
		SET mer.custom_songa_wallet_processed = 1
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
