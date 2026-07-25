"""Auto-process Songa wallets when M-Pesa Express reaches a terminal status.

frappe_mpsa_payments updates Express status via ``frappe.db.set_value``, which
does not fire document events. Wallet processing is hooked from
``update_mpesa_request_status`` (callback + status query). The 5-minute cron
remains a safety net for failed attempts and edge paths.
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


def apply_patches() -> None:
	"""Patch mpsa status writers so Songa wallets process on terminal status."""
	global _PATCHED
	if _PATCHED:
		return

	try:
		from frappe_mpsa_payments.utils import utils as mpesa_utils
	except ImportError:
		return

	original = mpesa_utils.update_mpesa_request_status
	if getattr(original, "_songa_wallet_patched", False):
		_PATCHED = True
		return

	wrapped = _wrapped_update_mpesa_request_status(original)
	wrapped._songa_wallet_patched = True
	mpesa_utils.update_mpesa_request_status = wrapped

	# Re-bind modules that imported the helper by name at import time.
	try:
		from frappe_mpsa_payments.frappe_mpsa_payments.api import m_pesa_api

		m_pesa_api.update_mpesa_request_status = wrapped
	except Exception:
		pass

	try:
		from frappe_mpsa_payments.frappe_mpsa_payments.api import mpesa_response_handler

		mpesa_response_handler.update_mpesa_request_status = wrapped
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
