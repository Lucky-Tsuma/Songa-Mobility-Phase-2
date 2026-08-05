import frappe

from songa_mobility_phase_2.songa_app_integration.utils.songa_webhook import send_songa_webhook
from songa_mobility_phase_2.songa_app_integration.utils.utils import (
	get_commission_balance_by_driver,
	get_energy_kwh_balance_by_driver,
	get_rental_days_balance_by_driver,
)

TRIGGERED_STATES = {"Approved", "Rejected"}


def _get_linked_wallet_recharge(doc):
	"""Return wallet recharge metadata linked to a commission Deduction ledger."""
	wallet = frappe.db.get_value(
		"Rental Days",
		{"driver_commission_ledger": doc.name},
		["name", "no_of_days", "amount", "status"],
		as_dict=True,
	)
	if wallet:
		return {
			"rental_day_id": wallet.name,
			"no_of_days": wallet.no_of_days,
			"wallet_amount": wallet.amount,
			"wallet_status": wallet.status,
		}

	wallet = frappe.db.get_value(
		"Energy KWh",
		{"driver_commission_ledger": doc.name},
		["name", "energy_qty", "amount", "status"],
		as_dict=True,
	)
	if wallet:
		return {
			"energy_kwh_id": wallet.name,
			"kwh": wallet.energy_qty,
			"wallet_amount": wallet.amount,
			"wallet_status": wallet.status,
		}

	return {}


def _wallet_balance_fields(driver_id, usage):
	"""Scalar wallet balances for Songa webhooks (matches post-recharge API shape)."""
	fields = {}
	if usage == "Rental days recharge":
		result = get_rental_days_balance_by_driver(driver_id=driver_id)
		if result.get("status") == "success":
			fields["rental_days_balance"] = result.get("total_rental_days", 0)
	elif usage == "Energy recharge":
		result = get_energy_kwh_balance_by_driver(driver_id=driver_id)
		if result.get("status") == "success":
			fields["energy_kwh_balance"] = result.get("total_kwh", 0)
	return fields


def _fail_linked_wallet_recharge(doc):
	"""Mark a linked wallet recharge Failed when a Deduction ledger is rejected."""
	if doc.transaction_type != "Deduction":
		return

	for wallet_doctype in ("Rental Days", "Energy KWh"):
		wallet_name = frappe.db.get_value(
			wallet_doctype,
			{"driver_commission_ledger": doc.name, "status": "In Progress"},
			"name",
		)
		if wallet_name:
			frappe.db.set_value(
				wallet_doctype,
				wallet_name,
				"status",
				"Failed",
				update_modified=True,
			)
			return


def _post_deduction_if_needed(doc):
	if doc.transaction_type == "Deduction" and doc.workflow_state == "Approved" and not doc.journal_entry:
		from songa_mobility_phase_2.songa_app_integration.utils.utils import (
			deduct_commission,
		)

		result = deduct_commission(doc.name)
		if isinstance(result, dict) and result.get("status") == "error":
			frappe.throw(result.get("message"))


def _post_allocation_if_needed(doc):
	if doc.transaction_type == "Allocation" and doc.workflow_state == "Approved" and not doc.journal_entry:
		from songa_mobility_phase_2.songa_app_integration.utils.utils import (
			allocate_commission,
		)

		result = allocate_commission(doc.name)
		if isinstance(result, dict) and result.get("status") == "error":
			frappe.throw(result.get("message"))


def handle_commission_ledger_workflow(doc, method):
	if doc.has_value_changed("workflow_state"):
		if doc.workflow_state == "Rejected":
			_fail_linked_wallet_recharge(doc)
		_post_deduction_if_needed(doc)
		_post_allocation_if_needed(doc)

	if not doc.has_value_changed("workflow_state") or doc.workflow_state not in TRIGGERED_STATES:
		return

	try:
		payload = {
			"driver_id": doc.driver,
			"transaction_type": doc.transaction_type,
			"amount": doc.amount,
			"commission_ledger": doc.name,
			"workflow_state": doc.workflow_state,
		}

		commission_balance = get_commission_balance_by_driver(driver_id=doc.driver)
		payload["commission_balance"] = commission_balance.get("balance", 0)

		if doc.transaction_type == "Deduction":
			usage = doc.usage
			payload["action_type"] = usage
			payload.update(_get_linked_wallet_recharge(doc))
			payload.update(_wallet_balance_fields(doc.driver, usage))
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
