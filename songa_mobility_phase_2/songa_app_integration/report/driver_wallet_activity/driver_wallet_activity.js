// Copyright (c) 2026, Lucky Tsuma and contributors
// For license information, please see license.txt

frappe.query_reports["Driver Wallet Activity"] = {
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
			default: frappe.datetime.add_months(frappe.datetime.now_date(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
		},
		{
			fieldname: "driver",
			label: __("Driver"),
			fieldtype: "Link",
			options: "Driver",
		},
		{
			fieldname: "wallet",
			label: __("Wallet"),
			fieldtype: "Select",
			options: ["All", "Commission", "Rental Days", "Energy"].join("\n"),
			default: "All",
		},
		{
			fieldname: "transaction_type",
			label: __("Transaction Type"),
			fieldtype: "Select",
			options: ["", "Allocation", "Deduction", "Recharge", "Usage"].join("\n"),
		},
		{
			fieldname: "status",
			label: __("Status (wallet)"),
			fieldtype: "Select",
			options: ["", "In Progress", "Completed", "Failed", "Cancelled"].join("\n"),
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (data && column.fieldname === "status") {
			const colorMap = {
				Completed: "green",
				Approved: "green",
				Failed: "red",
				Rejected: "red",
				Cancelled: "gray",
				"In Progress": "orange",
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
