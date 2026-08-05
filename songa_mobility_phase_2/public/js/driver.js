const getBalance = (frm) => {
	frappe.call({
		method: "songa_mobility_phase_2.songa_app_integration.utils.utils.get_overall_balance",
		freeze: true,
		freeze_message: "Retrieving overall balance...",
		args: {
			driver_id: frm.doc.name,
		},
		callback: function (r) {
			frappe.dom.unfreeze();
			if (r.message && r.message.status === "success") {
				const data = r.message.data;
				frappe.msgprint(`
                    <div>
                        <h4>Overall Balance</h4>
                        <p><strong>Commission:</strong> ${data.commission_balance}/=</p>
                        <p><strong>Rental Days:</strong> ${data.rental_days_balance} days</p>
                        <p><strong>Energy:</strong> ${data.energy_kwh_balance} kWh</p>
                    </div>
                `);
			} else {
				frappe.msgprint(
					"Failed to retrieve overall balance. Please check the error log for more details."
				);
			}
		},
		error: function () {
			frappe.dom.unfreeze();
			frappe.msgprint("An error occurred while retrieving overall balance.");
		},
	});
};

let driverParentSupplierGroup = null;

const loadDriverParentSupplierGroup = () => {
	return frappe.db
		.get_single_value("Songa Customization Settings", "driver_parent_supplier_group")
		.then((value) => {
			driverParentSupplierGroup = value;
		});
};

const filterSongaDrivers = (frm) => {
	frm.set_query("custom_supplier_group", function () {
		const filters = { is_group: 0 };
		if (driverParentSupplierGroup) {
			filters.parent_supplier_group = driverParentSupplierGroup;
		}
		return { filters };
	});
};

frappe.ui.form.on("Driver", {
	onload(frm) {
		loadDriverParentSupplierGroup().then(() => filterSongaDrivers(frm));
	},
	refresh(frm) {
		if (!frm.doc.__islocal) {
			frm.add_custom_button("View Overall Balance", () => {
				return getBalance(frm);
			});
		}
		if (!driverParentSupplierGroup) {
			loadDriverParentSupplierGroup().then(() => filterSongaDrivers(frm));
		} else {
			filterSongaDrivers(frm);
		}
	},
});
