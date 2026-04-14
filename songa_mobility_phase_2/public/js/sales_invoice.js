// Cache to hold the customer-derived values
const _salesInvoicecommissionDefaults = {
    branch: null,
    cost_center: null,
};

const clear_branch_and_cost_center = (frm) => {
    _salesInvoicecommissionDefaults.branch = null;
    _salesInvoicecommissionDefaults.cost_center = null;
    frm.set_value("branch", "");
    frm.set_value("cost_center", "");
};

frappe.ui.form.on("Sales Invoice", {
    customer: function (frm) {
        _salesInvoicecommissionDefaults.branch = null;
        _salesInvoicecommissionDefaults.cost_center = null;
        set_sales_invoice_branch_and_cost_center(frm);
    },

    // Guard: restore if something else clears or overwrites these fields
    branch: function (frm) {
        if (_salesInvoicecommissionDefaults.branch && frm.doc.branch !== _salesInvoicecommissionDefaults.branch) {
            frm.set_value("branch", _salesInvoicecommissionDefaults.branch);
        }
    },
    cost_center: function (frm) {
        if (_salesInvoicecommissionDefaults.cost_center && frm.doc.cost_center !== _salesInvoicecommissionDefaults.cost_center) {
            frm.set_value("cost_center", _salesInvoicecommissionDefaults.cost_center);
        }
    },
    validate: function (frm) {
        if (_salesInvoicecommissionDefaults.branch && frm.doc.branch !== _salesInvoicecommissionDefaults.branch) {
            frm.set_value("branch", _salesInvoicecommissionDefaults.branch);
        }

        if (_salesInvoicecommissionDefaults.cost_center && frm.doc.cost_center !== _salesInvoicecommissionDefaults.cost_center) {
            frm.set_value("cost_center", _salesInvoicecommissionDefaults.cost_center);
        }
    },
});

const set_sales_invoice_branch_and_cost_center = (frm) => {
    if (!frm.doc.customer) return clear_branch_and_cost_center(frm);

    return frappe.call({
        method: "songa_mobility_phase_2.songa_app_integration.utils.utils.get_linked_supplier",
        args: { customer: frm.doc.customer },
        callback: function (r) {
            if (!r.message) return clear_branch_and_cost_center(frm);

            return frappe.call({
                method: "songa_mobility_phase_2.songa_app_integration.utils.utils.get_branch_and_cost_center_by_supplier",
                args: { supplier: r.message },
                callback: function (res) {
                    if (!res.message) return clear_branch_and_cost_center(frm);

                    _salesInvoicecommissionDefaults.branch = res.message.branch || null;
                    _salesInvoicecommissionDefaults.cost_center = res.message.cost_center || null;

                    frm.set_value("branch", res.message.branch || "");
                    frm.set_value("cost_center", res.message.cost_center || "");
                },
                error: function () {
                    frappe.msgprint("An error occurred while retrieving supplier details.");
                }
            });
        },
        error: function () {
            frappe.msgprint("An error occurred while retrieving linked supplier.");
        }
    });
};