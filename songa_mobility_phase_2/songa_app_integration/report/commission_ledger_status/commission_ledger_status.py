# Copyright (c) 2026, Lucky Tsuma and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data)


def get_columns():
	return [
		{"fieldname": "posting_date", "label": "Date", "fieldtype": "Date", "width": 100},
		{
			"fieldname": "name",
			"label": "Ledger Entry",
			"fieldtype": "Link",
			"options": "Driver Commission Ledger",
			"width": 170,
		},
		{"fieldname": "driver", "label": "Driver", "fieldtype": "Link", "options": "Driver", "width": 120},
		{"fieldname": "driver_name", "label": "Driver Name", "fieldtype": "Data", "width": 150},
		{"fieldname": "transaction_type", "label": "Type", "fieldtype": "Data", "width": 100},
		{"fieldname": "usage", "label": "Usage", "fieldtype": "Data", "width": 150},
		{"fieldname": "amount", "label": "Amount", "fieldtype": "Currency", "width": 120},
		{"fieldname": "workflow_state", "label": "Status", "fieldtype": "Data", "width": 110},
		{
			"fieldname": "journal_entry",
			"label": "Journal Entry",
			"fieldtype": "Link",
			"options": "Journal Entry",
			"width": 160,
		},
	]


def get_data(filters):
	conditions = {}
	if filters.get("company"):
		conditions["company"] = filters.get("company")
	if filters.get("driver"):
		conditions["driver"] = filters.get("driver")
	if filters.get("transaction_type"):
		conditions["transaction_type"] = filters.get("transaction_type")
	if filters.get("workflow_state"):
		conditions["workflow_state"] = filters.get("workflow_state")
	else:
		# Default to the live (non-cancelled) approval pipeline.
		conditions["docstatus"] = ["<", 2]

	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters.get("from_date"), filters.get("to_date")]]
	elif filters.get("from_date"):
		conditions["posting_date"] = [">=", filters.get("from_date")]
	elif filters.get("to_date"):
		conditions["posting_date"] = ["<=", filters.get("to_date")]

	return frappe.get_all(
		"Driver Commission Ledger",
		filters=conditions,
		fields=[
			"name",
			"posting_date",
			"driver",
			"driver_name",
			"transaction_type",
			"usage",
			"amount",
			"workflow_state",
			"journal_entry",
		],
		order_by="posting_date desc, creation desc",
	)


def get_chart(data):
	counts = {}
	for row in data:
		state = row.get("workflow_state") or "Unknown"
		counts[state] = counts.get(state, 0) + 1
	if not counts:
		return None

	labels = list(counts.keys())
	return {
		"data": {"labels": labels, "datasets": [{"name": "Entries", "values": [counts[label] for label in labels]}]},
		"type": "donut",
	}
