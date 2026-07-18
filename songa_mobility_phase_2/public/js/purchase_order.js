// Cache to hold the customer-derived values
const _purchaseOrderCommissionDefaults = {
	branch: null,
	cost_center: null,
};

const clear_branch_and_cost_center_po = (frm) => {
	_purchaseOrderCommissionDefaults.branch = null;
	_purchaseOrderCommissionDefaults.cost_center = null;
	frm.set_value("branch", "");
	frm.set_value("cost_center", "");
};

frappe.ui.form.on("Purchase Order", {
	supplier: function (frm) {
		if (frm.doc.supplier) {
			set_purchase_order_branch_and_cost_center(frm);
		}
	},
	// Guard: restore if something else clears or overwrites these fields
	branch: function (frm) {
		if (
			_purchaseOrderCommissionDefaults.branch &&
			frm.doc.branch !== _purchaseOrderCommissionDefaults.branch
		) {
			frm.set_value("branch", _purchaseOrderCommissionDefaults.branch);
		}
	},
	cost_center: function (frm) {
		if (
			_purchaseOrderCommissionDefaults.cost_center &&
			frm.doc.cost_center !== _purchaseOrderCommissionDefaults.cost_center
		) {
			frm.set_value("cost_center", _purchaseOrderCommissionDefaults.cost_center);
		}
	},
	validate: function (frm) {
		if (
			_purchaseOrderCommissionDefaults.branch &&
			frm.doc.branch !== _purchaseOrderCommissionDefaults.branch
		) {
			frm.set_value("branch", _purchaseOrderCommissionDefaults.branch);
		}

		if (
			_purchaseOrderCommissionDefaults.cost_center &&
			frm.doc.cost_center !== _purchaseOrderCommissionDefaults.cost_center
		) {
			frm.set_value("cost_center", _purchaseOrderCommissionDefaults.cost_center);
		}
	},
});

const set_purchase_order_branch_and_cost_center = (frm) => {
	if (!frm.doc.supplier) return clear_branch_and_cost_center_po(frm);

	return frappe.call({
		method: "songa_mobility_phase_2.songa_app_integration.utils.utils.get_branch_and_cost_center_by_supplier",
		args: { supplier: frm.doc.supplier },
		callback: function (r) {
			if (r.message) {
				_purchaseOrderCommissionDefaults.branch = r.message.branch || null;
				_purchaseOrderCommissionDefaults.cost_center = r.message.cost_center || null;

				frm.set_value("branch", r.message.branch || "");
				frm.set_value("cost_center", r.message.cost_center || "");
			} else {
				return clear_branch_and_cost_center_po(frm);
			}
		},
		error: function () {
			frappe.msgprint("An error occurred while retrieving supplier details.");
		},
	});
};
