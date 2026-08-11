import frappe


def validate_wallet_status(doc):
	"""Enforce status rules for Rental Days / Energy KWh without breaking Usage create."""
	status = doc.status

	if doc.docstatus == 2 and status != "Cancelled":
		doc.status = "Cancelled"
		return

	# Allow new Usage docs to set Completed before submit (API insert then submit).
	if status == "Completed" and doc.docstatus == 0 and not doc.is_new():
		frappe.throw("Completed is only allowed on submitted documents.")

	if status == "Completed" and doc.docstatus == 0 and doc.is_new():
		if doc.transaction_type != "Usage":
			frappe.throw(
				"Completed on a new draft is only allowed for Usage. "
				"Recharges must stay In Progress until payment is confirmed."
			)


def on_wallet_cancel(doc):
	doc.db_set("status", "Cancelled", update_modified=False)


def validate_wallet_payment_links(doc):
	"""Ensure at most one payment channel is set on a Recharge."""
	if doc.transaction_type != "Recharge":
		return

	channels = []
	if doc.get("driver_commission_ledger"):
		channels.append("Driver Commission Ledger")
	if doc.get("mpesa_express_request"):
		channels.append("Mpesa Express Request")
	if doc.get("mpesa_c2b_payment_register"):
		channels.append("Mpesa C2B Payment Register")

	if len(channels) > 1:
		frappe.throw("A recharge can only use one payment channel. " f"Found: {', '.join(channels)}.")
