frappe.ui.form.on("Driver", {
    refresh(frm){
        frm.add_custom_button("View Commission Balance", () => {
            return getCommissionBalance(frm);
        });
    }
});

const getCommissionBalance = (frm) => {
    frappe.call({
        method: "songa_mobility_phase_2.songa_app_integration.utils.utils.get_commission_balance",
        freeze: true,
        freeze_message: "Retrieving commission balance...",
        args: {
            "driver_id": frm.doc.name
        },
        callback: function(r) {
            frappe.dom.unfreeze();
            if (r.message && r.message.status === "success") {
                const balance = r.message.balance || 0;
                frappe.msgprint(`Total commission balance for ${frm.doc.full_name} is ${balance}`);
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