# Copyright (c) 2026, Lucky Tsuma and contributors
# For license information, please see license.txt

import frappe

WALLET_LABELS = {
	"Driver Commission Ledger": "Commission",
	"Rental Days": "Rental Days",
	"Energy KWh": "Energy",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "posting_date", "label": "Date", "fieldtype": "Date", "width": 100},
		{"fieldname": "driver", "label": "Driver", "fieldtype": "Link", "options": "Driver", "width": 130},
		{"fieldname": "driver_name", "label": "Driver Name", "fieldtype": "Data", "width": 160},
		{"fieldname": "wallet", "label": "Wallet", "fieldtype": "Data", "width": 110},
		{"fieldname": "transaction_type", "label": "Type", "fieldtype": "Data", "width": 110},
		{"fieldname": "quantity", "label": "Qty", "fieldtype": "Float", "width": 90, "precision": 2},
		{"fieldname": "amount", "label": "Amount", "fieldtype": "Currency", "width": 120},
		{"fieldname": "payment_method", "label": "Payment Method", "fieldtype": "Data", "width": 120},
		{"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 110},
		{
			"fieldname": "reference_name",
			"label": "Reference",
			"fieldtype": "Dynamic Link",
			"options": "reference_doctype",
			"width": 150,
		},
		{"fieldname": "reference_doctype", "label": "Reference Type", "fieldtype": "Data", "width": 130},
	]


def get_data(filters):
	wallet = filters.get("wallet") or "All"
	rows = []

	if wallet in ("All", "Commission"):
		rows += get_commission_rows(filters)
	if wallet in ("All", "Rental Days"):
		rows += get_wallet_rows(filters, "Rental Days", "no_of_days")
	if wallet in ("All", "Energy"):
		rows += get_wallet_rows(filters, "Energy KWh", "energy_qty")

	if filters.get("transaction_type"):
		rows = [r for r in rows if r["transaction_type"] == filters.get("transaction_type")]

	rows.sort(key=lambda r: (r["posting_date"] or "", r["reference_name"]), reverse=True)
	return rows


def _common_filters(filters):
	conditions = {"docstatus": 1}
	if filters.get("company"):
		conditions["company"] = filters.get("company")
	if filters.get("driver"):
		conditions["driver"] = filters.get("driver")
	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters.get("from_date"), filters.get("to_date")]]
	elif filters.get("from_date"):
		conditions["posting_date"] = [">=", filters.get("from_date")]
	elif filters.get("to_date"):
		conditions["posting_date"] = ["<=", filters.get("to_date")]
	return conditions


def get_commission_rows(filters):
	conditions = _common_filters(filters)
	records = frappe.get_all(
		"Driver Commission Ledger",
		filters=conditions,
		fields=[
			"name",
			"posting_date",
			"driver",
			"driver_name",
			"transaction_type",
			"amount",
			"workflow_state",
		],
	)
	rows = []
	for record in records:
		rows.append(
			{
				"posting_date": record.posting_date,
				"driver": record.driver,
				"driver_name": record.driver_name,
				"wallet": WALLET_LABELS["Driver Commission Ledger"],
				"transaction_type": record.transaction_type,
				"quantity": None,
				"amount": record.amount,
				"payment_method": None,
				"status": record.workflow_state,
				"reference_name": record.name,
				"reference_doctype": "Driver Commission Ledger",
			}
		)
	return rows


def get_wallet_rows(filters, doctype, qty_field):
	conditions = _common_filters(filters)
	if filters.get("status"):
		conditions["status"] = filters.get("status")
	records = frappe.get_all(
		doctype,
		filters=conditions,
		fields=[
			"name",
			"posting_date",
			"driver",
			"driver_name",
			"transaction_type",
			f"{qty_field} as quantity",
			"amount",
			"status",
			"driver_commission_ledger",
			"mpesa_express_request",
		],
	)
	rows = []
	for record in records:
		rows.append(
			{
				"posting_date": record.posting_date,
				"driver": record.driver,
				"driver_name": record.driver_name,
				"wallet": WALLET_LABELS[doctype],
				"transaction_type": record.transaction_type,
				"quantity": record.quantity,
				"amount": record.amount,
				"payment_method": get_payment_method(record),
				"status": record.status,
				"reference_name": record.name,
				"reference_doctype": doctype,
			}
		)
	return rows


def get_payment_method(record):
	if record.get("mpesa_express_request"):
		return "M-Pesa"
	if record.get("driver_commission_ledger"):
		return "Commission"
	return None
