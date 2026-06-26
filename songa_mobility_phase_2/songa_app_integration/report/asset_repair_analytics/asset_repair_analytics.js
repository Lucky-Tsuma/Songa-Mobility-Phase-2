// Copyright (c) 2026, Lucky Tsuma and contributors
// For license information, please see license.txt

frappe.query_reports["Asset Repair Analytics"] = {
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
			default: frappe.datetime.add_months(frappe.datetime.now_date(), -6),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
		},
		{
			fieldname: "asset_type",
			label: __("Asset Type"),
			fieldtype: "Link",
			options: "Asset Type",
		},
		{
			fieldname: "severity_type",
			label: __("Severity Type"),
			fieldtype: "Link",
			options: "Severity Type",
		},
		{
			fieldname: "repair_status",
			label: __("Repair Status"),
			fieldtype: "Select",
			options: ["", "Pending", "Completed", "Cancelled"].join("\n"),
		},
		{
			fieldname: "workflow_state",
			label: __("Workflow State"),
			fieldtype: "Link",
			options: "Workflow State",
		},
		{
			fieldname: "asset",
			label: __("Asset"),
			fieldtype: "Link",
			options: "Asset",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (data && column.fieldname === "repair_status") {
			const colorMap = { Completed: "green", Cancelled: "gray", Pending: "orange" };
			const color = colorMap[value];
			if (color) {
				value = `<span style="color: ${color}; font-weight: 500;">${value}</span>`;
			}
		}

		return value;
	},
};
