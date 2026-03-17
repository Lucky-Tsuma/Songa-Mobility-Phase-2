import frappe

from .utils import process_mpesa_express_request


@frappe.whitelist(allow_guest=False)
def process_pending_mpesa_express_requests():
	pending_requests = frappe.get_all(
		"Mpesa Express Request",
		filters={
			"status": ("in", ["Completed", "Failed"]),
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
			frappe.log_error(frappe.get_traceback(), f"Failed to process Mpesa Express Request {request}")
			continue
