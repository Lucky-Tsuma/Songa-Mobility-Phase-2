// Copyright (c) 2026, Lucky Tsuma and contributors
// For license information, please see license.txt

frappe.ui.form.on("Songa Customization Settings", {
	onload(frm) {
        frm.set_query("expense_account", () => {
            return {
                filters: {
                    "root_type": "Expense",
                }
            }
        })

        frm.set_query("liability_account", () => {
            return {
                filters: {
                    "root_type": "Liability",
                }
            }
        })
	},
});
