import json

import frappe
import requests

from songa_mobility_phase_2.songa_app_integration.utils.utils import (
	get_commission_balance_by_driver,
	get_energy_kwh_balance_by_driver,
	get_rental_days_balance_by_driver,
)

TRIGGERED_STATES = {"Approved", "Rejected"}


def handle_commission_ledger_workflow(doc, method):
	if not doc.has_value_changed("workflow_state") or doc.workflow_state not in TRIGGERED_STATES:
		return

	try:
		url = frappe.get_single("Songa Customization Settings").songa_webhook_endpoint

		if not url:
			frappe.log_error(
				"Songa webhook endpoint not found, please check Songa Customization Settings",
				"Commission Ledger Workflow",
			)
			return

		# initiate logger
		frappe.utils.logger.set_log_level("INFO")
		songa_webhook_logger = frappe.logger("songa_webhook_log", allow_site=True, file_count=20)

		return_payload = {
			"driver_id": doc.driver,
			"transaction_type": doc.transaction_type,
			"amount": doc.amount,
			"commission_ledger": doc.name,
		}

		headers = {"Content-Type": "application/json"}

		commission_balance = get_commission_balance_by_driver(driver_id=doc.driver)
		return_payload["commission_balance"] = commission_balance.get("balance", 0)

		if doc.transaction_type == "Deduction":
			usage = doc.usage
			return_payload["usage"] = usage

			if usage == "Energy recharge":
				return_payload["energy_kwh_balance"] = get_energy_kwh_balance_by_driver(driver_id=doc.driver)
			elif usage == "Rental days recharge":
				return_payload["rental_days_balance"] = get_rental_days_balance_by_driver(
					driver_id=doc.driver
				)

			return_payload["deducted_amount"] = doc.amount

		data = json.dumps(return_payload)
		response = requests.post(url, data=data, headers=headers, verify=True)
		if response.status_code != 200:
			frappe.log_error(f"{response}", "Error sending data to webhook endpoint")
			return
		songa_webhook_logger.info(f"Driver Commission Ledger: {doc.name}. Response: {response}\n")
	except Exception as e:
		frappe.log_error(
			f"Error processing Commission Ledger for {doc.name}: {e!s}", "Commission Ledger Workflow"
		)
