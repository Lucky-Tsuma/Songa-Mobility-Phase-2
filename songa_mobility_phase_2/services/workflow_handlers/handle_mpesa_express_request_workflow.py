import frappe

from songa_mobility_phase_2.songa_app_integration.utils.utils import get_rental_days_balance_by_driver


def handle_mpesa_express_request_workflow(doc, method):
	try:
		if not doc.has_value_changed("status"):
			return

		if doc.status not in ("Completed", "Failed"):
			return

		if doc.reference_doctype != "Rental Days":
			return

		rental_days = frappe.get_doc("Rental Days", doc.reference_name)

		# Guard against duplicate triggers on an already-processed record
		if rental_days.docstatus != 0:
			return

		try:
			frappe.db.savepoint("mpesa_express_request")

			if doc.status == "Completed":
				rental_days.mpesa_express_request = doc.name
				rental_days.save(ignore_permissions=True)
				rental_days.submit()

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
				frappe.delete_doc("Rental Days", rental_days.name, ignore_permissions=True)

			frappe.db.commit()

		except Exception:
			frappe.db.rollback(save_point="mpesa_express_request")
			raise

		if doc.status == "Completed":
			balance = get_rental_days_balance_by_driver(driver_id=rental_days.driver)
			frappe.logger().info(
				f"Rental days recharged for driver {rental_days.driver}. "
				f"New balance: {balance.get('total_rental_days', 0)}"
			)
		else:
			frappe.logger().info(
				f"Rental days recharge cancelled for driver {rental_days.driver} "
				f"due to failed M-Pesa payment."
			)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Mpesa Express Request Workflow Error")
		frappe.throw(str(e))
