// Copyright (c) 2026, Lucky Tsuma and contributors
// For license information, please see license.txt

frappe.ui.form.on("Energy KWh", {
	refresh(frm) {
		frappe.songa_wallet_c2b.setup_form(frm);
	},
});
