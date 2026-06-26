# Copyright (c) 2026, Lucky Tsuma and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data)


def get_columns():
	return [
		{
			"fieldname": "name",
			"label": "Asset Repair",
			"fieldtype": "Link",
			"options": "Asset Repair",
			"width": 150,
		},
		{"fieldname": "asset", "label": "Asset", "fieldtype": "Link", "options": "Asset", "width": 130},
		{"fieldname": "asset_name", "label": "Asset Name", "fieldtype": "Data", "width": 150},
		{"fieldname": "custom_asset_type", "label": "Asset Type", "fieldtype": "Data", "width": 110},
		{"fieldname": "custom_severity_type", "label": "Severity", "fieldtype": "Data", "width": 100},
		{"fieldname": "repair_status", "label": "Repair Status", "fieldtype": "Data", "width": 110},
		{"fieldname": "workflow_state", "label": "Workflow State", "fieldtype": "Data", "width": 170},
		{"fieldname": "failure_date", "label": "Failure Date", "fieldtype": "Datetime", "width": 150},
		{"fieldname": "completion_date", "label": "Completion Date", "fieldtype": "Datetime", "width": 150},
		{"fieldname": "downtime", "label": "Downtime", "fieldtype": "Data", "width": 100},
		{"fieldname": "stock_consumption", "label": "Stock Used", "fieldtype": "Check", "width": 90},
		{"fieldname": "repair_cost", "label": "Repair Cost", "fieldtype": "Currency", "width": 120},
		{"fieldname": "total_repair_cost", "label": "Total Cost", "fieldtype": "Currency", "width": 120},
		{"fieldname": "cost_center", "label": "Cost Center", "fieldtype": "Link", "options": "Cost Center", "width": 130},
	]


def get_data(filters):
	conditions = [["docstatus", "<", 2]]
	if filters.get("company"):
		conditions.append(["company", "=", filters.get("company")])
	if filters.get("asset"):
		conditions.append(["asset", "=", filters.get("asset")])
	if filters.get("repair_status"):
		conditions.append(["repair_status", "=", filters.get("repair_status")])
	if filters.get("workflow_state"):
		conditions.append(["workflow_state", "=", filters.get("workflow_state")])
	if filters.get("asset_type"):
		conditions.append(["custom_asset_type_id", "=", filters.get("asset_type")])
	if filters.get("severity_type"):
		conditions.append(["custom_severity_type_id", "=", filters.get("severity_type")])
	if filters.get("from_date"):
		conditions.append(["failure_date", ">=", f"{filters.get('from_date')} 00:00:00"])
	if filters.get("to_date"):
		conditions.append(["failure_date", "<=", f"{filters.get('to_date')} 23:59:59"])

	return frappe.get_all(
		"Asset Repair",
		filters=conditions,
		fields=[
			"name",
			"asset",
			"asset_name",
			"custom_asset_type",
			"custom_severity_type",
			"repair_status",
			"workflow_state",
			"failure_date",
			"completion_date",
			"downtime",
			"stock_consumption",
			"repair_cost",
			"total_repair_cost",
			"cost_center",
		],
		order_by="failure_date desc",
	)


def get_chart(data):
	monthly = {}
	for row in data:
		if not row.get("failure_date"):
			continue
		period = getdate(row["failure_date"]).strftime("%Y-%m")
		monthly[period] = monthly.get(period, 0.0) + flt(row.get("total_repair_cost"))

	if not monthly:
		return None

	periods = sorted(monthly.keys())
	return {
		"data": {
			"labels": periods,
			"datasets": [{"name": "Total Repair Cost", "values": [monthly[period] for period in periods]}],
		},
		"type": "bar",
	}
