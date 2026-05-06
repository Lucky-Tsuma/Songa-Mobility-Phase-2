# Copyright (c) 2026, Lucky Tsuma and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	columns, data = get_columns(filters), get_data(filters)
	return columns, data


def get_data(filters=None):
	return []

def get_columns(filters=None):	
	columns = [
		{
			"label": _("Driver"),
			"fieldname": "driver",
			"fieldtype": "Link",
			"options": "Driver",
			"width": 150,
		},
		{
			"label": _("Driver Name"),
			"fieldname": "driver_name",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": _("Posting Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 150
		},
		{
			"label": _("Amount"),
			"fieldname": "amount",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"label": _("Transaction Type"),
			"fieldname": "transaction_type",
			"fieldtype": "Select",
			"options": ["All", "Allocation", "Deduction"],
			"width": 150
		}
	]
	
	if filters and filters.get("mode_of_payment") in ["All", "Commission"]:
		columns.append(
			{
				"label": _("Journal Entry"),
				"fieldname": "journal_entry",
				"fieldtype": "Link",
				"options": "Journal Entry",
				"width": 150
			}
		)

	if filters and filters.get("mode_of_payment") in ["All", "Mpesa"]:
		columns.append(
			{
				"label": _("Mpesa Transaction ID"),
				"fieldname": "mpesa_transaction_id",
				"fieldtype": "Link",
				"options": "    Mpesa Express Request",
				"width": 150
			}
		)

	if filters and filters.get("transaction_type") in ["All", "Deduction"]:
		columns.append(
			{
				"label": _("Usage"),
				"fieldname": "usage",
				"fieldtype": "Data",
				"width": 150
			}
		)

	return columns