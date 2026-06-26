# Copyright (c) 2026, Lucky Tsuma and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, getdate

WALLETS = {
	"Rental Days": "no_of_days",
	"Energy KWh": "energy_qty",
}
WALLET_LABELS = {"Rental Days": "Rental Days", "Energy KWh": "Energy"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	columns = get_columns()
	chart = get_chart(data)
	return columns, data, None, chart


def get_columns():
	return [
		{"fieldname": "period", "label": "Period", "fieldtype": "Data", "width": 110},
		{"fieldname": "wallet", "label": "Wallet", "fieldtype": "Data", "width": 110},
		{"fieldname": "payment_method", "label": "Payment Method", "fieldtype": "Data", "width": 130},
		{"fieldname": "total_count", "label": "Recharges", "fieldtype": "Int", "width": 100},
		{"fieldname": "completed_count", "label": "Completed", "fieldtype": "Int", "width": 100},
		{"fieldname": "failed_count", "label": "Failed", "fieldtype": "Int", "width": 90},
		{"fieldname": "success_rate", "label": "Success %", "fieldtype": "Percent", "width": 100},
		{"fieldname": "recharge_amount", "label": "Amount (Completed)", "fieldtype": "Currency", "width": 160},
		{"fieldname": "quantity", "label": "Qty (Completed)", "fieldtype": "Float", "width": 130, "precision": 2},
	]


def get_data(filters):
	wallet_filter = filters.get("wallet") or "All"
	method_filter = filters.get("payment_method") or "All"
	period_type = filters.get("period") or "Monthly"

	buckets = {}
	for doctype, qty_field in WALLETS.items():
		if wallet_filter not in ("All", WALLET_LABELS[doctype]):
			continue
		for record in fetch_recharges(filters, doctype, qty_field):
			method = get_payment_method(record)
			if method_filter != "All" and method != method_filter:
				continue

			period = get_period_label(record.posting_date, period_type)
			key = (period, WALLET_LABELS[doctype], method)
			bucket = buckets.setdefault(
				key,
				{
					"period": period,
					"wallet": WALLET_LABELS[doctype],
					"payment_method": method,
					"total_count": 0,
					"completed_count": 0,
					"failed_count": 0,
					"recharge_amount": 0.0,
					"quantity": 0.0,
				},
			)

			bucket["total_count"] += 1
			if record.status == "Completed":
				bucket["completed_count"] += 1
				bucket["recharge_amount"] += flt(record.amount)
				bucket["quantity"] += flt(record.quantity)
			elif record.status == "Failed":
				bucket["failed_count"] += 1

	rows = list(buckets.values())
	for row in rows:
		row["success_rate"] = (
			(row["completed_count"] / row["total_count"]) * 100 if row["total_count"] else 0
		)

	rows.sort(key=lambda r: (r["period"], r["wallet"], r["payment_method"] or ""))
	return rows


def fetch_recharges(filters, doctype, qty_field):
	conditions = {"docstatus": 1, "transaction_type": "Recharge"}
	if filters.get("company"):
		conditions["company"] = filters.get("company")
	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters.get("from_date"), filters.get("to_date")]]
	elif filters.get("from_date"):
		conditions["posting_date"] = [">=", filters.get("from_date")]
	elif filters.get("to_date"):
		conditions["posting_date"] = ["<=", filters.get("to_date")]

	return frappe.get_all(
		doctype,
		filters=conditions,
		fields=[
			"posting_date",
			"status",
			"amount",
			f"{qty_field} as quantity",
			"driver_commission_ledger",
			"mpesa_express_request",
		],
	)


def get_payment_method(record):
	if record.get("mpesa_express_request"):
		return "M-Pesa"
	if record.get("driver_commission_ledger"):
		return "Commission"
	return "Unspecified"


def get_period_label(date_value, period_type):
	if not date_value:
		return "Unknown"
	date_value = getdate(date_value)
	if period_type == "Daily":
		return date_value.strftime("%Y-%m-%d")
	if period_type == "Weekly":
		iso = date_value.isocalendar()
		return f"{iso[0]}-W{iso[1]:02d}"
	return date_value.strftime("%Y-%m")


def get_chart(data):
	periods = sorted({row["period"] for row in data})
	if not periods:
		return None

	methods = ["M-Pesa", "Commission"]
	totals = {method: {period: 0.0 for period in periods} for method in methods}
	for row in data:
		method = row["payment_method"] if row["payment_method"] in methods else "Commission"
		totals[method][row["period"]] += flt(row["recharge_amount"])

	datasets = [
		{"name": method, "values": [totals[method][period] for period in periods]} for method in methods
	]

	return {
		"data": {"labels": periods, "datasets": datasets},
		"type": "bar",
		"barOptions": {"stacked": 1},
	}
