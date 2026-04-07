const getBalance = (frm) => {
    frappe.call({
        method: "songa_mobility_phase_2.songa_app_integration.utils.utils.get_overall_balance",
        freeze: true,
        freeze_message: "Retrieving overall balance...",
        args: {
            "driver_id": frm.doc.name
        },
        callback: function(r) {
            frappe.dom.unfreeze();
            if (r.message && r.message.status === "success") {
                data = r.message.data;
                frappe.msgprint(`
                    <div>
                        <h4>Overall Balance</h4>
                        <p><strong>Commission:</strong> ${data.commission_balance}/=</p>
                        <p><strong>Rental Days:</strong> ${data.rental_days_balance} days</p>
                        <p><strong>Energy:</strong> ${data.energy_kwh_balance} kWh</p>  
                    </div>
                `);
            } else {
                frappe.msgprint("Failed to retrieve overall balance. Please check the error log for more details.");
            }
        },
        error: function() {
            frappe.dom.unfreeze();
            frappe.msgprint("An error occurred while retrieving overall balance.");
        }
    });
};

frappe.ui.form.on("Driver", {
    refresh(frm) {
        frm.add_custom_button("View Overall Balance", () => {
            return getBalance(frm);
        });
    }
});