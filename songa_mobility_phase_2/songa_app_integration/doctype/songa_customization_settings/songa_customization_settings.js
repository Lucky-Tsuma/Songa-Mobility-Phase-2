// Copyright (c) 2026, Lucky Tsuma and contributors
// For license information, please see license.txt

frappe.ui.form.on("Songa Customization Settings", {
	onload(frm) {
		frm.set_query("driver_commission_account", () => {
			return {
				filters: {
					root_type: "Expense",
				},
			};
		});
	},
});
