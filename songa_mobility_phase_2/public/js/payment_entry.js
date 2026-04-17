// Cache to hold the customer-derived values
const _paymentEntrycommissionDefaults = {
    branch: null,
    cost_center: null,
};

const clear_branch_and_cost_center_pe = (frm) => {
    _paymentEntrycommissionDefaults.branch = null;
    _paymentEntrycommissionDefaults.cost_center = null;
    frm.set_value("branch", "");
    frm.set_value("cost_center", "");
};

frappe.ui.form.on("Payment Entry", {
    party: function (frm) {
        if (frm.doc.party_type === "Supplier") {
            set_payment_entry_branch_and_cost_center(frm);
        }
    },
    // Guard: restore if something else clears or overwrites these fields
    branch: function (frm) {
        if (_paymentEntrycommissionDefaults.branch && frm.doc.branch !== _paymentEntrycommissionDefaults.branch) {
            frm.set_value("branch", _paymentEntrycommissionDefaults.branch);
        }
    },
    cost_center: function (frm) {
        if (_paymentEntrycommissionDefaults.cost_center && frm.doc.cost_center !== _paymentEntrycommissionDefaults.cost_center) {
            frm.set_value("cost_center", _paymentEntrycommissionDefaults.cost_center);
        }
    },
    validate: function (frm) {
        if (_paymentEntrycommissionDefaults.branch && frm.doc.branch !== _paymentEntrycommissionDefaults.branch) {
            frm.set_value("branch", _paymentEntrycommissionDefaults.branch);
        }

        if (_paymentEntrycommissionDefaults.cost_center && frm.doc.cost_center !== _paymentEntrycommissionDefaults.cost_center) {
            frm.set_value("cost_center", _paymentEntrycommissionDefaults.cost_center);
        }
    },
});

const set_payment_entry_branch_and_cost_center = (frm) => {
    if (!frm.doc.party) return clear_branch_and_cost_center_pe(frm);

    return frappe.call({
        method: "songa_mobility_phase_2.songa_app_integration.utils.utils.get_branch_and_cost_center_by_supplier",
        args: { supplier: frm.doc.party },
        callback: function (r) {
            if (r.message) {
                let supplier_doc = r.message;

                _paymentEntrycommissionDefaults.branch = supplier_doc.branch || null;
                _paymentEntrycommissionDefaults.cost_center = supplier_doc.cost_center || null;

                frm.set_value("branch", supplier_doc.branch || "");
                frm.set_value("cost_center", supplier_doc.cost_center || "");
            } else {
                return clear_branch_and_cost_center_pe(frm);
            }
        },
        error: function () {
            frappe.msgprint("An error occurred while retrieving supplier details.");
        }
    });
};