// Copyright (c) 2026, Lucky Tsuma and contributors
// For license information, please see license.txt

frappe.query_reports["Wallet Recharge Analytics"] = {
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
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Select",
			options: ["Daily", "Weekly", "Monthly"].join("\n"),
			default: "Monthly",
		},
		{
			fieldname: "wallet",
			label: __("Wallet"),
			fieldtype: "Select",
			options: ["All", "Rental Days", "Energy"].join("\n"),
			default: "All",
		},
		{
			fieldname: "payment_method",
			label: __("Payment Method"),
			fieldtype: "Select",
			options: ["All", "M-Pesa", "Commission"].join("\n"),
			default: "All",
		},
	],
};
