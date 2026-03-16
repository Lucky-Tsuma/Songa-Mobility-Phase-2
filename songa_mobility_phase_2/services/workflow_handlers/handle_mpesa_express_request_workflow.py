import frappe

from songa_mobility_phase_2.songa_app_integration.utils.utils import (
	get_energy_kwh_balance_by_driver,
	get_rental_days_balance_by_driver,
)


def handle_mpesa_express_request_workflow(doc, method):
	try:
		if not doc.has_value_changed("status"):
			return

		if doc.status not in ("Completed", "Failed"):
			return

		if doc.reference_doctype not in ("Rental Days", "Energy KWh"):
			return

		reference_doctype = doc.reference_doctype
		reference_doc = frappe.get_doc(reference_doctype, doc.reference_name)

		# Guard against duplicate triggers on an already-processed record
		if reference_doc.docstatus != 0:
			return

		try:
			frappe.db.savepoint("mpesa_express_request")

			if doc.status == "Completed":
				reference_doc.mpesa_express_request = doc.name
				reference_doc.save(ignore_permissions=True)
				reference_doc.submit()

			elif doc.status == "Failed":
				# Clear the back-reference on Mpesa Express Request first so
				# Frappe's link integrity check no longer blocks the deletion
				frappe.db.sql(
					"""
					UPDATE `tabMpesa Express Request`
					SET reference_doctype = NULL, reference_name = NULL
					WHERE name = %s
					""",
					doc.name,
				)
				frappe.delete_doc(reference_doctype, reference_doc.name, ignore_permissions=True)

			frappe.db.commit()

		except Exception:
			frappe.db.rollback(save_point="mpesa_express_request")
			raise

		if doc.status == "Completed":
			balance = (
				get_rental_days_balance_by_driver(driver_id=reference_doc.driver).get("total_rental_days", 0)
				if reference_doctype == "Rental Days"
				else get_energy_kwh_balance_by_driver(driver_id=reference_doc.driver).get("total_kwh", 0)
			)
			frappe.logger().info(
				f"{reference_doctype} recharged for driver {reference_doc.driver}. " f"New balance: {balance}"
			)
		else:
			frappe.logger().info(
				f"{reference_doctype} recharge cancelled for driver {reference_doc.driver} "
				f"due to failed M-Pesa payment."
			)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Mpesa Express Request Workflow Error")
		frappe.throw(str(e))
