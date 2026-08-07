import frappe


def execute():
	names = [
		"Mpesa Express Request-custom_songa_wallet_processed",
		"Mpesa Express Request-custom_songa_wallet_attempt_count",
		"Mpesa Express Request-custom_songa_wallet_last_attempt_on",
		"Mpesa Express Request-custom_songa_wallet_process_status",
		"Mpesa Express Request-custom_songa_journal_entry",
		"Mpesa C2B Payment Register-custom_songa_wallet_section",
		"Mpesa C2B Payment Register-custom_songa_reference_doctype",
		"Mpesa C2B Payment Register-custom_songa_reference_name",
		"Mpesa C2B Payment Register-custom_songa_wallet_processed",
		"Mpesa C2B Payment Register-custom_songa_wallet_attempt_count",
		"Mpesa C2B Payment Register-custom_songa_wallet_last_attempt_on",
		"Mpesa C2B Payment Register-custom_songa_wallet_process_status",
		"Mpesa C2B Payment Register-custom_songa_journal_entry",
	]
	for name in names:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, force=True)
