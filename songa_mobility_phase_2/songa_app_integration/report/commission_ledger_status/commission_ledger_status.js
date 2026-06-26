// Copyright (c) 2026, Lucky Tsuma and contributors
// For license information, please see license.txt

frappe.query_reports["Commission Ledger Status"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.now_date(), -3),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
		},
		{
			fieldname: "workflow_state",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Pending", "Approved", "Rejected", "Cancelled"].join("\n"),
		},
		{
			fieldname: "transaction_type",
			label: __("Transaction Type"),
			fieldtype: "Select",
			options: ["", "Allocation", "Deduction"].join("\n"),
		},
		{
			fieldname: "driver",
			label: __("Driver"),
			fieldtype: "Link",
			options: "Driver",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (data && column.fieldname === "workflow_state") {
			const colorMap = {
				Approved: "green",
				Rejected: "red",
				Cancelled: "gray",
				Pending: "orange",
			};
			const color = colorMap[value];
			if (color) {
				value = `<span style="color: ${color}; font-weight: 500;">${value}</span>`;
			}
		}

		return value;
	},
};
