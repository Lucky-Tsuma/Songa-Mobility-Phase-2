frappe.ui.form.on("Payment Entry", {
    party: function (frm) {
        if (frm.doc.party_type === "Supplier") {
            set_payment_entry_branch_and_cost_center(frm);
        }
    }
});

const set_payment_entry_branch_and_cost_center = (frm) => {
    if (!frm.doc.party) return;

    return frappe.call({
        method: "songa_mobility_phase_2.songa_app_integration.utils.utils.get_branch_and_cost_center_by_supplier",
        args: { supplier: frm.doc.party },
        callback: function (r) {
            if (r.message) {
                supplier_doc = r.message;
                frm.set_value("branch", supplier_doc.branch);
                frm.set_value("cost_center", supplier_doc.cost_center);
            } else {
                return;
            }
        },
        error: function () {
            frappe.msgprint("An error occurred while retrieving supplier details.");
        }
    });
};