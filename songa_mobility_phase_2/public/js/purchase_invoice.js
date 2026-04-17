// Cache to hold the customer-derived values
const _purchaseInvoiceCommissionDefaults = {
    branch: null,
    cost_center: null,
};

const clear_branch_and_cost_center_pi = (frm) => {
    _purchaseInvoiceCommissionDefaults.branch = null;
    _purchaseInvoiceCommissionDefaults.cost_center = null;
    frm.set_value("branch", "");
    frm.set_value("cost_center", "");
};

frappe.ui.form.on("Purchase Invoice", {
    supplier: function (frm) {
        if (frm.doc.supplier) {
            set_purchase_invoice_branch_and_cost_center(frm);
        }
    },
    // Guard: restore if something else clears or overwrites these fields
    branch: function (frm) {
        if (_purchaseInvoiceCommissionDefaults.branch && frm.doc.branch !== _purchaseInvoiceCommissionDefaults.branch) {
            frm.set_value("branch", _purchaseInvoiceCommissionDefaults.branch);
        }
    },
    cost_center: function (frm) {
        if (_purchaseInvoiceCommissionDefaults.cost_center && frm.doc.cost_center !== _purchaseInvoiceCommissionDefaults.cost_center) {
            frm.set_value("cost_center", _purchaseInvoiceCommissionDefaults.cost_center);
        }
    },
    validate: function (frm) {
        if (_purchaseInvoiceCommissionDefaults.branch && frm.doc.branch !== _purchaseInvoiceCommissionDefaults.branch) {
            frm.set_value("branch", _purchaseInvoiceCommissionDefaults.branch);
        }

        if (_purchaseInvoiceCommissionDefaults.cost_center && frm.doc.cost_center !== _purchaseInvoiceCommissionDefaults.cost_center) {
            frm.set_value("cost_center", _purchaseInvoiceCommissionDefaults.cost_center);
        }
    },
});

const set_purchase_invoice_branch_and_cost_center = (frm) => {
    if (!frm.doc.supplier) return clear_branch_and_cost_center_pi(frm);

    return frappe.call({
        method: "songa_mobility_phase_2.songa_app_integration.utils.utils.get_branch_and_cost_center_by_supplier",
        args: { supplier: frm.doc.supplier },
        callback: function (r) {
            if (r.message) {

                _purchaseInvoiceCommissionDefaults.branch = r.message.branch || null;
                _purchaseInvoiceCommissionDefaults.cost_center = r.message.cost_center || null;

                frm.set_value("branch", r.message.branch || "");
                frm.set_value("cost_center", r.message.cost_center || "");
            } else {
                return clear_branch_and_cost_center_pi(frm);
            }
        },
        error: function () {
            frappe.msgprint("An error occurred while retrieving supplier details.");
        }
    });
};