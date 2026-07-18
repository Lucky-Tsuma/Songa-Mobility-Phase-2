# Copyright (c) 2026, Lucky Tsuma and contributors
# For license information, please see license.txt

import frappe

SONGA_REFERENCE_DOCTYPES = ["Rental Days", "Energy KWh"]
WALLET_LABELS = {"Rental Days": "Rental Days", "Energy KWh": "Energy"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"fieldname": "creation",
			"label": "Request Date",
			"fieldtype": "Datetime",
			"width": 160,
		},
		{
			"fieldname": "name",
			"label": "STK Request",
			"fieldtype": "Link",
			"options": "Mpesa Express Request",
			"width": 170,
		},
		{
			"fieldname": "driver",
			"label": "Driver",
			"fieldtype": "Link",
			"options": "Driver",
			"width": 120,
		},
		{
			"fieldname": "driver_name",
			"label": "Driver Name",
			"fieldtype": "Data",
			"width": 150,
		},
		{"fieldname": "wallet", "label": "Wallet", "fieldtype": "Data", "width": 100},
		{
			"fieldname": "reference_name",
			"label": "Reference",
			"fieldtype": "Dynamic Link",
			"options": "reference_doctype",
			"width": 130,
		},
		{
			"fieldname": "phone_number",
			"label": "Phone",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"fieldname": "amount",
			"label": "Amount",
			"fieldtype": "Currency",
			"width": 110,
		},
		{"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 110},
		{
			"fieldname": "transaction_date",
			"label": "Completed On",
			"fieldtype": "Datetime",
			"width": 160,
		},
		{
			"fieldname": "reference_doctype",
			"label": "Reference Type",
			"fieldtype": "Data",
			"width": 120,
		},
	]


def get_data(filters):
	conditions = {"reference_doctype": ["in", SONGA_REFERENCE_DOCTYPES]}
	if filters.get("status"):
		conditions["status"] = filters.get("status")
	if filters.get("wallet") and filters.get("wallet") != "All":
		label_to_doctype = {v: k for k, v in WALLET_LABELS.items()}
		conditions["reference_doctype"] = label_to_doctype.get(filters.get("wallet"))
	if filters.get("from_date") and filters.get("to_date"):
		conditions["creation"] = [
			"between",
			[filters.get("from_date"), filters.get("to_date")],
		]
	elif filters.get("from_date"):
		conditions["creation"] = [">=", filters.get("from_date")]
	elif filters.get("to_date"):
		conditions["creation"] = ["<=", filters.get("to_date")]

	requests = frappe.get_all(
		"Mpesa Express Request",
		filters=conditions,
		fields=[
			"name",
			"creation",
			"reference_doctype",
			"reference_name",
			"phone_number",
			"amount",
			"status",
			"transaction_date",
		],
		order_by="creation desc",
	)

	driver_map = get_driver_map(requests)

	rows = []
	for request in requests:
		driver_info = driver_map.get((request.reference_doctype, request.reference_name), {})
		driver_id = driver_info.get("driver")

		if filters.get("driver") and driver_id != filters.get("driver"):
			continue

		rows.append(
			{
				"creation": request.creation,
				"name": request.name,
				"driver": driver_id,
				"driver_name": driver_info.get("driver_name"),
				"wallet": WALLET_LABELS.get(request.reference_doctype, request.reference_doctype),
				"reference_name": request.reference_name,
				"reference_doctype": request.reference_doctype,
				"phone_number": request.phone_number,
				"amount": request.amount,
				"status": request.status,
				"transaction_date": request.transaction_date,
			}
		)
	return rows


def get_driver_map(requests):
	"""Resolve driver/driver_name for each referenced wallet record in one query per doctype."""
	names_by_doctype = {}
	for request in requests:
		if request.reference_name:
			names_by_doctype.setdefault(request.reference_doctype, set()).add(request.reference_name)

	driver_map = {}
	for doctype, names in names_by_doctype.items():
		records = frappe.get_all(
			doctype,
			filters={"name": ["in", list(names)]},
			fields=["name", "driver", "driver_name"],
		)
		for record in records:
			driver_map[(doctype, record.name)] = {
				"driver": record.driver,
				"driver_name": record.driver_name,
			}
	return driver_map
