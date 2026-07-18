"""These are the single source of truth for driver wallet balances. The whitelisted
endpoints in `utils.py`, the Driver form button, webhooks, and the analytics
reports/dashboards all build on top of these so the numbers stay consistent.
"""

import frappe
from erpnext.accounts.utils import get_balance_on

COMPLETED = "Completed"
RECHARGE = "Recharge"
USAGE = "Usage"


def get_commission_balance(supplier, company):
	"""Commission payable for a supplier as a positive number (0 when flat)."""
	raw_balance = get_balance_on(
		party_type="Supplier",
		party=supplier,
		date=frappe.utils.today(),
		company=company,
	)
	return -raw_balance if raw_balance != 0 else 0


def get_rental_days_balance(driver_id):
	"""Net rental days (completed recharges minus completed usage) for a driver."""
	recharged = (
		frappe.get_value(
			"Rental Days",
			{
				"driver": driver_id,
				"docstatus": 1,
				"transaction_type": RECHARGE,
				"status": COMPLETED,
			},
			"sum(no_of_days)",
		)
		or 0
	)
	used = (
		frappe.get_value(
			"Rental Days",
			{
				"driver": driver_id,
				"docstatus": 1,
				"transaction_type": USAGE,
				"status": COMPLETED,
			},
			"sum(no_of_days)",
		)
		or 0
	)
	return recharged - used


def get_energy_kwh_balance(driver_id):
	"""Net energy kWh (completed recharges minus completed usage) for a driver."""
	recharged = (
		frappe.get_value(
			"Energy KWh",
			{
				"driver": driver_id,
				"docstatus": 1,
				"transaction_type": RECHARGE,
				"status": COMPLETED,
			},
			"sum(energy_qty)",
		)
		or 0
	)
	used = (
		frappe.get_value(
			"Energy KWh",
			{
				"driver": driver_id,
				"docstatus": 1,
				"transaction_type": USAGE,
				"status": COMPLETED,
			},
			"sum(energy_qty)",
		)
		or 0
	)
	return recharged - used
