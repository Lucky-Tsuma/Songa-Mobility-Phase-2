import unittest
from unittest.mock import MagicMock, patch

import frappe

from songa_mobility_phase_2.songa_app_integration.overrides import mpesa_express


class TestMpesaExpressAutoProcess(unittest.TestCase):
	def setUp(self):
		mpesa_express._PATCHED = False

	def tearDown(self):
		mpesa_express._PATCHED = False

	def _wallet_doc(self, **overrides):
		doc = MagicMock()
		doc.name = "MER-001"
		doc.reference_doctype = "Rental Days"
		doc.status = "Completed"
		doc.custom_songa_wallet_processed = 0
		doc.custom_songa_wallet_process_status = "Pending"
		for key, value in overrides.items():
			setattr(doc, key, value)
		return doc

	@patch("songa_mobility_phase_2.songa_app_integration.utils.utils.process_mpesa_express_request")
	@patch("frappe.get_doc")
	def test_auto_process_runs_for_completed_wallet(self, get_doc, process):
		get_doc.return_value = self._wallet_doc()

		mpesa_express.auto_process_mpesa_express_wallet("MER-001")

		process.assert_called_once()
		self.assertEqual(process.call_args.args[0].name, "MER-001")

	@patch("songa_mobility_phase_2.songa_app_integration.utils.utils.process_mpesa_express_request")
	@patch("frappe.get_doc")
	def test_auto_process_skips_non_wallet_reference(self, get_doc, process):
		get_doc.return_value = self._wallet_doc(reference_doctype="Payment Request")

		mpesa_express.auto_process_mpesa_express_wallet("MER-001")

		process.assert_not_called()

	@patch("songa_mobility_phase_2.songa_app_integration.utils.utils.process_mpesa_express_request")
	@patch("frappe.get_doc")
	def test_auto_process_skips_already_processed(self, get_doc, process):
		get_doc.return_value = self._wallet_doc(custom_songa_wallet_processed=1)

		mpesa_express.auto_process_mpesa_express_wallet("MER-001")

		process.assert_not_called()

	@patch("songa_mobility_phase_2.songa_app_integration.utils.utils.record_mpesa_wallet_processing_failure")
	@patch(
		"songa_mobility_phase_2.songa_app_integration.utils.utils.process_mpesa_express_request",
		side_effect=Exception("JE failed"),
	)
	@patch("frappe.get_doc")
	@patch("frappe.log_error")
	def test_auto_process_records_failure(self, _log, get_doc, process, record_failure):
		get_doc.return_value = self._wallet_doc()

		mpesa_express.auto_process_mpesa_express_wallet("MER-001")

		record_failure.assert_called_once_with("MER-001")

	def test_wrapped_status_update_triggers_auto_process(self):
		original = MagicMock()
		wrapped = mpesa_express._wrapped_update_mpesa_request_status(original)

		with patch.object(mpesa_express, "auto_process_mpesa_express_wallet") as auto_process:
			wrapped("MER-001", {"status": "Completed", "result_code": "0"})

		original.assert_called_once_with("MER-001", {"status": "Completed", "result_code": "0"})
		auto_process.assert_called_once_with("MER-001")

	def test_wrapped_status_update_ignores_in_progress(self):
		original = MagicMock()
		wrapped = mpesa_express._wrapped_update_mpesa_request_status(original)

		with patch.object(mpesa_express, "auto_process_mpesa_express_wallet") as auto_process:
			wrapped("MER-001", {"status": "In Progress"})

		original.assert_called_once()
		auto_process.assert_not_called()
