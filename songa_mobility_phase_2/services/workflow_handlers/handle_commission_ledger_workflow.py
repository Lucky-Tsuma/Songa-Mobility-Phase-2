import frappe

from songa_mobility_phase_2.songa_app_integration.utils.songa_webhook import send_songa_webhook
from songa_mobility_phase_2.songa_app_integration.utils.utils import (
	get_commission_balance_by_driver,
	get_energy_kwh_balance_by_driver,
	get_rental_days_balance_by_driver,
)

TRIGGERED_STATES = {"Approved", "Rejected"}


def _post_deduction_if_needed(doc):
	if doc.transaction_type == "Deduction" and doc.workflow_state == "Approved" and not doc.journal_entry:
		from songa_mobility_phase_2.songa_app_integration.utils.utils import (
			deduct_commission,
		)

		result = deduct_commission(doc.name)
		if isinstance(result, dict) and result.get("status") == "error":
			frappe.throw(result.get("message"))


def handle_commission_ledger_workflow(doc, method):
	if doc.has_value_changed("workflow_state"):
		_post_deduction_if_needed(doc)

	if not doc.has_value_changed("workflow_state") or doc.workflow_state not in TRIGGERED_STATES:
		return

	try:
		payload = {
			"driver_id": doc.driver,
			"transaction_type": doc.transaction_type,
			"amount": doc.amount,
			"commission_ledger": doc.name,
		}

		commission_balance = get_commission_balance_by_driver(driver_id=doc.driver)
		payload["commission_balance"] = commission_balance.get("balance", 0)

		if doc.transaction_type == "Deduction":
			usage = doc.usage
			payload["action_type"] = usage

			if usage == "Energy recharge":
				payload["energy_kwh_balance"] = get_energy_kwh_balance_by_driver(driver_id=doc.driver)
			elif usage == "Rental days recharge":
				payload["rental_days_balance"] = get_rental_days_balance_by_driver(driver_id=doc.driver)
		elif doc.transaction_type == "Allocation":
			payload["action_type"] = "Approved Commission"
		else:
			return

		if not payload.get("action_type"):
			return

		send_songa_webhook(payload, context="Commission Ledger Workflow")
	except Exception as e:
		frappe.log_error(
			f"Error processing Commission Ledger for {doc.name}: {e!s}",
			"Commission Ledger Workflow",
		)
