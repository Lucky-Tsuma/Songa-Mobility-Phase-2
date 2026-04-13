frappe.ui.form.on("Sales Invoice", {
    customer: function (frm) {
        set_sales_invoice_branch_and_cost_center(frm);
    }
});

const set_sales_invoice_branch_and_cost_center = (frm) => {
    if (!frm.doc.customer) return;
    return frappe.call({
        method: "songa_mobility_phase_2.songa_app_integration.utils.utils.get_linked_supplier",
        args: { customer: frm.doc.customer },
        callback: function (r) {
            if (r.message) {
                return frappe.call({
                    method: "songa_mobility_phase_2.songa_app_integration.utils.utils.get_branch_and_cost_center_by_supplier",
                    args: { supplier: r.message },
                    callback: function (res) {
                        if (res.message) {
                            frm.set_value("branch", res.message.branch);
                            frm.set_value("cost_center", res.message.cost_center);
                        }
                    },
                    error: function () {
                        frappe.msgprint("An error occurred while retrieving supplier details.");
                    }
                });
            }
        },
        error: function () {
            frappe.msgprint("An error occurred while retrieving linked supplier.");
        }
    });
};