import unittest
from unittest.mock import MagicMock, patch

from songa_mobility_phase_2.songa_app_integration.events.events import on_asset_repair_update


class TestOnAssetRepairUpdate(unittest.TestCase):
	def _repair_doc(
		self,
		*,
		workflow_state,
		previous_state="Approved",
		repair_status="Pending",
		stock_consumption=0,
		stock_items=None,
	):
		doc = MagicMock()
		doc.name = "ACC-ASR-2026-00054"
		doc.custom_asset_repair_id = "repair-0999"
		doc.asset = "EASVRM/SON/0209"
		doc.asset_name = "Songa 1.0-Asset"
		doc.custom_asset_type = "TRIKE"
		doc.custom_severity_type = "MEDIUM"
		doc.failure_date = "2026-09-22 01:22:55"
		doc.completion_date = "2026-09-22 15:54:51"
		doc.repair_status = repair_status
		doc.workflow_state = workflow_state
		doc.stock_consumption = stock_consumption
		doc.total_repair_cost = 233.33
		doc.description = "to fix the canopy well"
		doc.actions_performed = "welding"
		doc.stock_items = stock_items or []
		doc.has_value_changed.side_effect = lambda field: field == "workflow_state"
		before = MagicMock()
		before.workflow_state = previous_state
		doc.get_doc_before_save.return_value = before
		return doc

	@patch("songa_mobility_phase_2.songa_app_integration.events.events.send_songa_webhook")
	def test_completed_sends_service_completed(self, send_webhook):
		doc = self._repair_doc(workflow_state="Completed", repair_status="Completed")

		on_asset_repair_update(doc, "on_update")

		send_webhook.assert_called_once()
		payload, kwargs = send_webhook.call_args.args[0], send_webhook.call_args.kwargs
		self.assertEqual(payload["action_type"], "Service Completed")
		self.assertEqual(payload["repair_status"], "Completed")
		self.assertEqual(payload["workflow_state"], "Completed")
		self.assertEqual(kwargs["context"], "Asset Repair Completion")

	@patch("songa_mobility_phase_2.songa_app_integration.events.events.send_songa_webhook")
	def test_rejected_sends_service_rejected_even_if_repair_status_completed(self, send_webhook):
		doc = self._repair_doc(
			workflow_state="Rejected",
			previous_state="Pending Approval HM",
			repair_status="Completed",
		)

		on_asset_repair_update(doc, "on_update")

		send_webhook.assert_called_once()
		payload, kwargs = send_webhook.call_args.args[0], send_webhook.call_args.kwargs
		self.assertEqual(payload["action_type"], "Service Rejected")
		self.assertEqual(payload["repair_status"], "Completed")
		self.assertEqual(payload["workflow_state"], "Rejected")
		self.assertEqual(kwargs["context"], "Asset Repair Rejection")

	@patch("songa_mobility_phase_2.songa_app_integration.events.events.send_songa_webhook")
	def test_cancelled_sends_service_cancelled(self, send_webhook):
		doc = self._repair_doc(
			workflow_state="Cancelled",
			previous_state="Completed",
			repair_status="Cancelled",
		)

		on_asset_repair_update(doc, "on_update")

		send_webhook.assert_called_once()
		payload, kwargs = send_webhook.call_args.args[0], send_webhook.call_args.kwargs
		self.assertEqual(payload["action_type"], "Service Cancelled")
		self.assertEqual(payload["workflow_state"], "Cancelled")
		self.assertEqual(kwargs["context"], "Asset Repair Cancellation")

	@patch("songa_mobility_phase_2.songa_app_integration.events.events.send_songa_webhook")
	def test_approved_does_not_send_webhook(self, send_webhook):
		doc = self._repair_doc(workflow_state="Approved", previous_state="Pending Approval HM")

		on_asset_repair_update(doc, "on_update")

		send_webhook.assert_not_called()

	@patch("songa_mobility_phase_2.songa_app_integration.events.events.send_songa_webhook")
	def test_no_workflow_change_skips_webhook(self, send_webhook):
		doc = self._repair_doc(workflow_state="Completed")
		doc.has_value_changed.return_value = False
		doc.has_value_changed.side_effect = None

		on_asset_repair_update(doc, "on_update")

		send_webhook.assert_not_called()

	@patch("songa_mobility_phase_2.songa_app_integration.events.events.send_songa_webhook")
	def test_stock_items_included_when_stock_consumption(self, send_webhook):
		item = MagicMock()
		item.item_code = "KSC 000051"
		item.warehouse = "Magena EASVRM - EASVRM"
		item.valuation_rate = 233.33
		item.custom_uom = "Nos"
		item.consumed_quantity = "1"
		item.total_value = 233.33

		doc = self._repair_doc(
			workflow_state="Rejected",
			previous_state="Pending Approval HM",
			repair_status="Completed",
			stock_consumption=1,
			stock_items=[item],
		)

		on_asset_repair_update(doc, "on_update")

		payload = send_webhook.call_args.args[0]
		self.assertEqual(len(payload["stock_items"]), 1)
		self.assertEqual(payload["stock_items"][0]["item_code"], "KSC 000051")


if __name__ == "__main__":
	unittest.main()
