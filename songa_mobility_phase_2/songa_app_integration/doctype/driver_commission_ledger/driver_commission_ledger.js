frappe.ui.form.on("Driver Commission Ledger", {
    before_workflow_action(frm) {
        if (frm.selected_workflow_action === "Approve" && frm.doc.transaction_type === "Allocation") {
            return allocateCommission(frm);
        }
    },
});

const allocateCommission = (frm) => {
    return new Promise((resolve, reject) => {
        frappe.call({
            method: "songa_mobility_phase_2.songa_app_integration.utils.utils.allocate_commission",
            args: {
                driver_commission_ledger_name: frm.doc.name
            },
            callback: function(r) {
                if (r.message && r.message.status === "success") {
                    frappe.msgprint("Commission allocated successfully");
                    resolve();
                } else {
                    frappe.msgprint("Failed to allocate commission. Please check the error log for more details.");
                    frappe.dom.unfreeze();
                    reject();
                }
            },
            error: function() {
                frappe.msgprint("An error occurred while allocating commission.");
                frappe.dom.unfreeze();
                reject();
            }
        });
    });
}