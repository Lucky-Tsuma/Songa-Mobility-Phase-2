// Copyright (c) 2026, Lucky Tsuma and contributors
// For license information, please see license.txt

frappe.ui.form.on("Service Entry", {
	before_save: function (frm) {
		update_total(frm);
	},
});

frappe.ui.form.on("Inventory Item", {
	quantity: function (frm, cdt, cdn) {
		calculate_amount(frm, cdt, cdn);
	},
	rate: function (frm, cdt, cdn) {
		calculate_amount(frm, cdt, cdn);
	},
});

function calculate_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const amount = (row.quantity || 0) * (row.rate || 0);
	frappe.model.set_value(cdt, cdn, "amount", amount);
	update_total(frm);
}

function update_total(frm) {
	let total = 0;
	(frm.doc.inventory_items || []).forEach((row) => {
		total += row.amount || 0;
	});
	frm.set_value("total_amount", total);
}
