frappe.ui.form.on("Wallet Request", {
    refresh(frm){
        if (frm.doc.wallet_type == "Driver rental trips" && frm.doc.request_type == "trip_commission") {
            frm.add_custom_button("View Commission Balance", () => {
                getCommissionBalance(frm);
            });
        }
    },
    before_workflow_action(frm) {
        if (frm.selected_workflow_action === "Approve") {

            if (frm.doc.wallet_type === "Driver commission") {
                return allocateCommission(frm);
            }

            if (frm.doc.wallet_type === "Driver rental trips" && frm.doc.request_type === "trip_commission") {
                return deductCommission(frm);
            }
        }
    },
});

const allocateCommission = (frm) => {
    return new Promise((resolve, reject) => {
        frappe.call({
            method: "from songa_mobility_phase_2.songa_app_integration.utils.utils.allocate_commission",
            args: {
                wallet_request_name: frm.doc.name
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

const deductCommission = (frm) => {
    return new Promise((resolve, reject) => {
        frappe.call({
            method: "from songa_mobility_phase_2.songa_app_integration.utils.utils.deduct_commission",
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

const getCommissionBalance = (frm) => {
    frappe.call({
        method: "songa_mobility_phase_2.songa_app_integration.utils.utils.get_commission_balance",
        freeze: true,
        freeze_message: "Retrieving commission balance...",
        args: {
            "driver_id": frm.doc.driver
        },
        callback: function(r) {
            frappe.dom.unfreeze();
            if (r.message && r.message.status === "success") {
                const balance = r.message.balance || 0;
                frappe.msgprint(`Total commission balance for ${frm.doc.driver_name} is ${balance}`);
            } else {
                frappe.msgprint("Failed to retrieve commission balance. Please check the error log for more details.");
            }
        },
        error: function() {
            frappe.dom.unfreeze();
            frappe.msgprint("An error occurred while retrieving commission balance.");
        }
    });
}