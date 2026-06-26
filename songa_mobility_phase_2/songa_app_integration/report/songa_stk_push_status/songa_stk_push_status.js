// Copyright (c) 2026, Lucky Tsuma and contributors
// For license information, please see license.txt

frappe.query_reports["Songa STK Push Status"] = {
	filters: [
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
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Pending", "Completed", "Failed"].join("\n"),
		},
		{
			fieldname: "wallet",
			label: __("Wallet"),
			fieldtype: "Select",
			options: ["All", "Rental Days", "Energy"].join("\n"),
			default: "All",
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

		if (data && column.fieldname === "status") {
			const colorMap = { Completed: "green", Failed: "red", Pending: "orange" };
			const color = colorMap[value];
			if (color) {
				value = `<span style="color: ${color}; font-weight: 500;">${value}</span>`;
			}
		}

		return value;
	},
};
