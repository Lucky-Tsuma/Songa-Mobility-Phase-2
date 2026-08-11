import frappe


def execute():
	settings = frappe.get_single("Songa Customization Settings")
	if settings.get("driver_parent_supplier_group"):
		return

	default_group = "Drivers / Collectors"
	if frappe.db.exists("Supplier Group", default_group):
		settings.driver_parent_supplier_group = default_group
		settings.save(ignore_permissions=True)
