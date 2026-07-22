import frappe

from songa_mobility_phase_2.songa_app_integration.patches.backfill_mpesa_wallet_processed import (
	ensure_mpesa_wallet_custom_fields,
)


def execute():
	"""Initialize wallet process-status fields introduced for capped M-Pesa retries."""
	ensure_mpesa_wallet_custom_fields()

	if not frappe.db.has_column("Mpesa Express Request", "custom_songa_wallet_process_status"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabMpesa Express Request`
		SET custom_songa_wallet_process_status = 'Processed',
			custom_songa_wallet_attempt_count = IFNULL(custom_songa_wallet_attempt_count, 0)
		WHERE IFNULL(custom_songa_wallet_processed, 0) = 1
		  AND IFNULL(custom_songa_wallet_process_status, '') IN ('', 'Pending')
		"""
	)

	frappe.db.sql(
		"""
		UPDATE `tabMpesa Express Request`
		SET custom_songa_wallet_process_status = 'Pending',
			custom_songa_wallet_attempt_count = IFNULL(custom_songa_wallet_attempt_count, 0)
		WHERE docstatus = 1
		  AND reference_doctype IN ('Rental Days', 'Energy KWh')
		  AND IFNULL(custom_songa_wallet_processed, 0) = 0
		  AND IFNULL(custom_songa_wallet_process_status, '') = ''
		"""
	)
