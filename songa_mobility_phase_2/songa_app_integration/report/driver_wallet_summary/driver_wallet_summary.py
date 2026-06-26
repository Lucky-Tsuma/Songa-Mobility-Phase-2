# Copyright (c) 2026, Lucky Tsuma and contributors
# For license information, please see license.txt

import frappe

from songa_mobility_phase_2.songa_app_integration.report_helpers import (
	get_commission_balance,
	get_energy_kwh_balance,
	get_rental_days_balance,
)

WALLET_DOCTYPES = ("Driver Commission Ledger", "Rental Days", "Energy KWh")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"fieldname": "driver",
			"label": "Driver",
			"fieldtype": "Link",
			"options": "Driver",
			"width": 140,
		},
		{
			"fieldname": "driver_name",
			"label": "Driver Name",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"fieldname": "commission_balance",
			"label": "Commission (KES)",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"fieldname": "rental_days_balance",
			"label": "Rental Days",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"fieldname": "energy_kwh_balance",
			"label": "Energy (kWh)",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"fieldname": "last_activity",
			"label": "Last Activity",
			"fieldtype": "Date",
			"width": 120,
		},
	]


def get_data(filters):
	company = filters.get("company") or frappe.defaults.get_user_default("Company")

	driver_filters = {"transporter": ["is", "set"]}
	if filters.get("driver"):
		driver_filters["name"] = filters.get("driver")

	drivers = frappe.get_all(
		"Driver",
		filters=driver_filters,
		fields=["name", "full_name", "transporter"],
		order_by="full_name asc",
	)

	data = []
	for driver in drivers:
		commission = 0
		if company and driver.transporter:
			try:
				commission = get_commission_balance(driver.transporter, company)
			except Exception:
				# A single driver's GL lookup failing should not break the whole report
				frappe.log_error(frappe.get_traceback(), "Driver Wallet Summary - Commission Balance")
				commission = 0

		data.append(
			{
				"driver": driver.name,
				"driver_name": driver.full_name,
				"commission_balance": commission,
				"rental_days_balance": get_rental_days_balance(driver.name),
				"energy_kwh_balance": get_energy_kwh_balance(driver.name),
				"last_activity": get_last_activity(driver.name),
			}
		)

	return data


def get_last_activity(driver_id):
	dates = []
	for doctype in WALLET_DOCTYPES:
		latest = frappe.db.get_value(
			doctype, {"driver": driver_id, "docstatus": 1}, "max(posting_date)"
		)
		if latest:
			dates.append(latest)
	return max(dates) if dates else None
