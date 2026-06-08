const set_asset_repair_branch_and_cost_center = (frm) => {
	if (!frm.doc.asset) {
		frm.set_value("branch", "");
		frm.set_value("cost_center", "");
		return;
	}

	frappe.db.get_value(
		"Asset",
		frm.doc.asset,
		["cost_center", "branch", "custom_branch"],
		(r) => {
			if (!r) return;

			frm.set_value("cost_center", r.cost_center || "");
			frm.set_value("branch", r.custom_branch || r.branch || "");
		}
	);
};

frappe.ui.form.on("Asset Repair", {
	asset(frm) {
		set_asset_repair_branch_and_cost_center(frm);
	},
});
