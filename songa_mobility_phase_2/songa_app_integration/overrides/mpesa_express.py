"""Auto-process Songa wallets when M-Pesa Express reaches a terminal status.

frappe_mpsa_payments updates Express status via ``frappe.db.set_value``, which
does not fire document events. Wallet processing is hooked from
``update_mpesa_request_status`` (callback + status query). The 5-minute cron
remains a safety net for failed attempts and edge paths.

Also patches ``handle_successful_transaction`` so Payment Request STK flows
create a Payment Entry before Webshop's ``on_payment_authorized`` can zero
outstanding via Phone-channel ``set_as_paid``.
"""

from __future__ import annotations

import frappe

_PATCHED = False


def auto_process_mpesa_express_wallet(name: str) -> None:
	"""Process a terminal Express request linked to a Songa wallet, if needed."""
	if not name:
		return

	try:
		doc = frappe.get_doc("Mpesa Express Request", name)
	except frappe.DoesNotExistError:
		return

	if doc.reference_doctype not in ("Rental Days", "Energy KWh"):
		return

	if doc.status not in ("Completed", "Failed"):
		return

	if getattr(doc, "custom_songa_wallet_processed", 0):
		return

	process_status = getattr(doc, "custom_songa_wallet_process_status", None) or "Pending"
	if process_status == "Abandoned":
		return

	from songa_mobility_phase_2.songa_app_integration.utils.utils import (
		process_mpesa_express_request,
		record_mpesa_wallet_processing_failure,
	)

	try:
		process_mpesa_express_request(doc)
	except Exception:
		record_mpesa_wallet_processing_failure(name)
		frappe.log_error(
			frappe.get_traceback(),
			f"Auto-process Mpesa Express Request {name} failed",
		)


def _wrapped_update_mpesa_request_status(original):
	def update_mpesa_request_status(name, status_data):
		original(name, status_data)
		status = (status_data or {}).get("status")
		if status in ("Completed", "Failed"):
			auto_process_mpesa_express_wallet(name)

	return update_mpesa_request_status


def _handle_payment_request_successful_transaction(request_doc, settings):
	"""Reconcile a completed Express request linked to a Payment Request.

	Skips ``on_payment_authorized`` before Payment Entry creation. With Webshop
	enabled, that hook calls ``set_as_paid()``; for ``payment_channel == "Phone"``
	ERPNext only sets outstanding to 0 / status Paid and does not create a PE,
	so the subsequent ``create_payment_entry()`` fails allocation validation.
	"""
	from frappe_mpsa_payments.utils.utils import (
		log_and_throw_error,
		set_mpesa_request_reconciled,
	)

	if "erpnext" not in frappe.get_installed_apps():
		return

	payment_request = frappe.get_doc("Payment Request", request_doc.reference_name)

	if payment_request.reference_doctype == "Sales Invoice":
		invoice = frappe.get_doc("Sales Invoice", payment_request.reference_name)
		if invoice.docstatus == 0:
			try:
				invoice.submit()
			except Exception:
				log_and_throw_error("Payment Request Submission Error", request_doc.name)

	try:
		payment_request.create_payment_entry()
	except Exception:
		log_and_throw_error("Payment Entry Creation Error", request_doc.name)

	try:
		if settings.auto_create_sales_invoice and payment_request.reference_doctype == "Sales Order":
			from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

			si = make_sales_invoice(payment_request.reference_name, ignore_permissions=True)
			si.allocate_advances_automatically = True
			si = si.insert(ignore_permissions=True)
			si.submit()
	except Exception:
		log_and_throw_error("Sales Invoice Creation Error", request_doc.name)

	frappe.db.set_value("Payment Request", payment_request.name, "status", "Paid")
	set_mpesa_request_reconciled(request_doc)


def _wrapped_handle_successful_transaction(original):
	def handle_successful_transaction(request_doc, settings):
		if request_doc.get("reference_doctype") == "Payment Request":
			_handle_payment_request_successful_transaction(request_doc, settings)
			return
		return original(request_doc, settings)

	return handle_successful_transaction


def apply_patches() -> None:
	"""Patch mpsa helpers used by STK callback / status query / reconcile."""
	global _PATCHED
	if _PATCHED:
		return

	try:
		from frappe_mpsa_payments.utils import utils as mpesa_utils
	except ImportError:
		return

	status_original = mpesa_utils.update_mpesa_request_status
	reconcile_original = mpesa_utils.handle_successful_transaction

	already_status = getattr(status_original, "_songa_wallet_patched", False)
	already_reconcile = getattr(reconcile_original, "_songa_pr_reconcile_patched", False)
	if already_status and already_reconcile:
		_PATCHED = True
		return

	if not already_status:
		status_wrapped = _wrapped_update_mpesa_request_status(status_original)
		status_wrapped._songa_wallet_patched = True
		mpesa_utils.update_mpesa_request_status = status_wrapped
	else:
		status_wrapped = status_original

	if not already_reconcile:
		reconcile_wrapped = _wrapped_handle_successful_transaction(reconcile_original)
		reconcile_wrapped._songa_pr_reconcile_patched = True
		mpesa_utils.handle_successful_transaction = reconcile_wrapped
	else:
		reconcile_wrapped = reconcile_original

	# Re-bind modules that imported helpers by name at import time.
	try:
		from frappe_mpsa_payments.frappe_mpsa_payments.api import m_pesa_api

		m_pesa_api.update_mpesa_request_status = status_wrapped
		m_pesa_api.handle_successful_transaction = reconcile_wrapped
	except Exception:
		pass

	try:
		from frappe_mpsa_payments.frappe_mpsa_payments.api import mpesa_response_handler

		mpesa_response_handler.update_mpesa_request_status = status_wrapped
		mpesa_response_handler.handle_successful_transaction = reconcile_wrapped
	except Exception:
		pass

	try:
		from frappe_mpsa_payments.frappe_mpsa_payments.doctype.mpesa_express_request import (
			mpesa_express_request,
		)

		mpesa_express_request.handle_successful_transaction = reconcile_wrapped
	except Exception:
		pass

	_PATCHED = True


@frappe.whitelist(allow_guest=True)
def stk_push_callback(**kwargs):
	"""Ensure Songa patches are active, then run the mpsa STK callback."""
	apply_patches()

	from frappe_mpsa_payments.frappe_mpsa_payments.api.m_pesa_api import (
		stk_push_callback as original_stk_push_callback,
	)

	original_stk_push_callback(**kwargs)
