import frappe

from songa_mobility_phase_2.songa_app_integration.utils.songa_webhook import (
	process_failed_songa_webhook_retries,
)

from .utils import (
	process_mpesa_express_request,
)

MPESA_WALLET_TERMINAL_STATUSES = ("Completed", "Failed")
MPESA_WALLET_PROCESS_BATCH_SIZE = 50
MPESA_WALLET_STALE_MINUTES = 30


def get_unprocessed_mpesa_express_requests(limit=None):
	"""Return terminal Express requests linked to Rental Days/Energy KWh wallets."""
	return frappe.db.sql(
		"""
		SELECT DISTINCT mer.name, mer.modified
		FROM `tabMpesa Express Request` mer
		LEFT JOIN `tabRental Days` rd
			ON rd.mpesa_express_request = mer.name
			AND rd.docstatus = 1
			AND rd.transaction_type = 'Recharge'
		LEFT JOIN `tabEnergy KWh` ek
			ON ek.mpesa_express_request = mer.name
			AND ek.docstatus = 1
			AND ek.transaction_type = 'Recharge'
		WHERE mer.docstatus = 1
		  AND mer.status IN ('Completed', 'Failed')
		  AND (rd.name IS NOT NULL OR ek.name IS NOT NULL)
		ORDER BY mer.modified ASC
		LIMIT %s
		""",
		(limit or MPESA_WALLET_PROCESS_BATCH_SIZE,),
		as_dict=True,
	)


def _log_stale_mpesa_requests(requests):
	cutoff = frappe.utils.add_to_date(None, minutes=-MPESA_WALLET_STALE_MINUTES)
	for request in requests:
		if request.modified and request.modified < cutoff:
			frappe.log_error(
				message=(
					f"Mpesa Express Request {request.name} reached a terminal status at "
					f"{request.modified} but wallet processing has not completed "
					"after scheduled retries."
				),
				title="Stale Mpesa Express Request",
			)


def retry_failed_songa_webhooks():
	try:
		process_failed_songa_webhook_retries()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Failed to process Songa webhook retries")


@frappe.whitelist(allow_guest=False)
def process_pending_mpesa_express_requests():
	requests = get_unprocessed_mpesa_express_requests()
	if not requests:
		return

	_log_stale_mpesa_requests(requests)

	for request in requests:
		try:
			doc = frappe.get_doc("Mpesa Express Request", request.name)
			process_mpesa_express_request(doc)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Failed to process Mpesa Express Request {request.name}",
			)
			continue
