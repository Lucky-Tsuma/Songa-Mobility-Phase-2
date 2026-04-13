frappe.ui.form.on("Sales Invoice", {
    customer: function (frm) {
        set_branch_and_cost_center(frm);
    }
});

const set_branch_and_cost_center = (frm) => {
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
                            supplier_doc = res.message;
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

            } else {
                return;
            }
        },
        error: function () {
            frappe.msgprint("An error occurred while retrieving linked supplier.");
        }
    });
};