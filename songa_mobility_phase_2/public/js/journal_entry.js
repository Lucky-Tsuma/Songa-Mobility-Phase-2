frappe.ui.form.on("Journal Entry Account", {
	party: function (frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (row.party_type === "Supplier" && row.party) {
			set_je_account_branch_and_cost_center(frm, row);
		}
	},
});

const set_je_account_branch_and_cost_center = (frm, row) => {
	return frappe.call({
		method: "songa_mobility_phase_2.songa_app_integration.utils.utils.get_branch_and_cost_center_by_supplier",
		args: { supplier: row.party },
		callback: function (r) {
			if (r.message) {
				frappe.model.set_value(row.doctype, row.name, "branch", r.message.branch);
				frappe.model.set_value(
					row.doctype,
					row.name,
					"cost_center",
					r.message.cost_center
				);
				frm.refresh_field("accounts");
			} else {
				return;
			}
		},
		error: function () {
			frappe.msgprint("An error occurred while retrieving supplier details.");
		},
	});
};
