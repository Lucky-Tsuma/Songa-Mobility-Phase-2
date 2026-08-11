// Copyright (c) 2026, Lucky Tsuma and contributors
// For license information, please see license.txt

frappe.ui.form.on("Songa Customization Settings", {
	onload(frm) {
		const expenseAccountQuery = () => ({
			filters: {
				root_type: "Expense",
			},
		});

		for (const field of [
			"driver_commission_account",
			"lease_to_own",
			"internal_consumption",
		]) {
			frm.set_query(field, expenseAccountQuery);
		}

		frm.set_query("driver_parent_supplier_group", () => ({
			filters: {
				is_group: 1,
			},
		}));
	},
});
