frappe.ui.form.on("Driver Commission Ledger", {
    before_workflow_action(frm) {
        if (frm.selected_workflow_action === "Approve") {

            if (frm.doc.transaction_type === "Allocation") {
                return allocateCommission(frm);
            }
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

// TODO: Remove unused function
const deductCommission = (frm) => {
    return new Promise((resolve, reject) => {
        frappe.call({
            method: "songa_mobility_phase_2.songa_app_integration.utils.utils.deduct_commission",
            args: {
                wallet_request_name: frm.doc.name
            },
            callback: function(r) {
                if (r.message && r.message.status === "success") {
                    resolve();
                    setTimeout(() => {
                        frappe.msgprint("Commission deducted successfully, new trip created.");
                    }, 1000); // wait for frappe alert to close before showing success message
                } else {
                    frappe.msgprint(r.message);
                    frappe.dom.unfreeze();
                    reject();
                }
            },
            error: function() {
                frappe.msgprint("An error occurred while deducting commission.");
                frappe.dom.unfreeze();
                reject();
            }
        });
    });
}