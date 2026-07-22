import frappe

from songa_mobility_phase_2.songa_app_integration.utils.songa_webhook import (
	process_failed_songa_webhook_retries,
)

from .utils import (
	MAX_MPESA_WALLET_ATTEMPTS,
	MPESA_WALLET_RETRY_INTERVAL_MINUTES,
	process_mpesa_express_request,
	record_mpesa_wallet_processing_failure,
)

MPESA_WALLET_REFERENCE_DOCTYPES = ("Rental Days", "Energy KWh")
MPESA_WALLET_TERMINAL_STATUSES = ("Completed", "Failed")
MPESA_WALLET_PROCESS_BATCH_SIZE = 50
MPESA_WALLET_STALE_MINUTES = 30


def get_unprocessed_mpesa_express_requests(limit=None):
	"""Return submitted wallet M-Pesa requests that still need Songa processing."""
	cutoff = frappe.utils.add_to_date(None, minutes=-MPESA_WALLET_RETRY_INTERVAL_MINUTES)
	return frappe.get_all(
		"Mpesa Express Request",
		filters={
			"status": ("in", list(MPESA_WALLET_TERMINAL_STATUSES)),
			"docstatus": 1,
			"reference_doctype": ("in", list(MPESA_WALLET_REFERENCE_DOCTYPES)),
			"custom_songa_wallet_processed": 0,
			"custom_songa_wallet_process_status": "Pending",
			"custom_songa_wallet_attempt_count": ("<", MAX_MPESA_WALLET_ATTEMPTS),
		},
		or_filters=[
			["custom_songa_wallet_last_attempt_on", "is", "not set"],
			["custom_songa_wallet_last_attempt_on", "<=", cutoff],
		],
		fields=["name", "modified", "custom_songa_wallet_attempt_count"],
		order_by="modified asc",
		limit=limit or MPESA_WALLET_PROCESS_BATCH_SIZE,
	)


def _log_stale_mpesa_requests(requests):
	cutoff = frappe.utils.add_to_date(None, minutes=-MPESA_WALLET_STALE_MINUTES)
	for request in requests:
		if request.modified and request.modified < cutoff:
			frappe.log_error(
				message=(
					f"Mpesa Express Request {request.name} reached a terminal status at "
					f"{request.modified} but wallet processing has not completed "
					f"(attempt {request.custom_songa_wallet_attempt_count or 0}/"
					f"{MAX_MPESA_WALLET_ATTEMPTS})."
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
			record_mpesa_wallet_processing_failure(request.name)
			frappe.log_error(
				frappe.get_traceback(),
				f"Failed to process Mpesa Express Request {request.name}",
			)
			continue
