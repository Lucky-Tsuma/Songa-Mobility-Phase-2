import frappe

from songa_mobility_phase_2.songa_app_integration.utils.songa_webhook import (
	process_failed_songa_webhook_retries,
)

from .utils import process_mpesa_express_request


def retry_failed_songa_webhooks():
	try:
		process_failed_songa_webhook_retries()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Failed to process Songa webhook retries")


@frappe.whitelist(allow_guest=False)
def process_pending_mpesa_express_requests():
	pending_requests = frappe.get_all(
		"Mpesa Express Request",
		filters={
			"status": ("in", ["Completed", "Failed"]),
			"docstatus": 1,
			"reference_doctype": ("in", ["Rental Days", "Energy KWh"]),
			"modified": (">=", frappe.utils.add_to_date(None, minutes=-15)),
		},
		pluck="name",
	)
	for request in pending_requests:
		try:
			doc = frappe.get_doc("Mpesa Express Request", request)
			process_mpesa_express_request(doc)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Failed to process Mpesa Express Request {request}",
			)
			continue
