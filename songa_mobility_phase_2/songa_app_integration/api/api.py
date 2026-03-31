import json
import re

import frappe
from frappe.model.workflow import apply_workflow

from ..utils.utils import (
	deduct_commission,
	get_commission_balance_by_driver,
	get_energy_kwh_balance_by_driver,
	get_rental_days_balance_by_driver,
)


def check_for_empty_payload():
	if not frappe.request.data:
		frappe.local.response["http_status_code"] = 400
		return {"status": "error", "message": "No data provided"}

	data = json.loads(frappe.request.data)

	if not data:
		frappe.local.response["http_status_code"] = 400
		return {"status": "error", "message": "No data provided"}

	return data


def check_for_empty_values(data, required_fields):
	missing = [f for f in required_fields if not data.get(f)]
	if missing:
		raise ValueError(f"Missing required fields: {', '.join(missing)}")


def validate_phone_number(phone_number=None):
	if not phone_number or len(phone_number) < 9:
		return False

	number = phone_number.strip().replace(" ", "")

	if not re.match(r"^(?:\+254|254|0)(7\d{8}|1\d{8})$", number):
		return False

	return True


@frappe.whitelist(allow_guest=False)
def allocate_commission():
	try:
		data = check_for_empty_payload()

		if isinstance(data, dict) and data.get("status") == "error":
			return data

		driver_id = data.get("driver_id")
		company = data.get("company")
		amount = data.get("amount")

		check_for_empty_values(data, ["driver_id", "amount"])

		driver = frappe.db.get_value("Driver", driver_id, "name")

		if not driver:
			frappe.local.response["http_status_code"] = 404
			return {"status": "error", "message": "Driver not found"}

		try:
			amount = float(amount)
			if amount <= 0:
				raise ValueError
		except (TypeError, ValueError):
			frappe.local.response["http_status_code"] = 400
			return {"status": "error", "message": "A valid positive amount is required"}

		driver_commission_ledger = frappe.get_doc(
			{
				"doctype": "Driver Commission Ledger",
				"company": company or frappe.defaults.get_user_default("company"),
				"driver": driver,
				"amount": amount,
				"transaction_type": "Allocation",
			}
		)
		driver_commission_ledger.insert()
		frappe.db.commit()

		return {
			"status": "success",
			"message": "Commission allocation ledger created, please await approval.",
			"data": {
				"name": driver_commission_ledger.name,
				"driver": driver_commission_ledger.driver,
				"amount": driver_commission_ledger.amount,
				"transaction_type": driver_commission_ledger.transaction_type,
				"company": driver_commission_ledger.company,
			},
		}

	except Exception as e:
		frappe.local.response["http_status_code"] = 500
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def recharge_rental_days():
	try:
		data = check_for_empty_payload()

		if isinstance(data, dict) and data.get("status") == "error":
			return data

		driver_id = data.get("driver_id")
		company = data.get("company")
		amount = data.get("amount")
		no_of_days = data.get("no_of_days")
		payment_method = data.get("payment_method")
		phone_number = data.get("phone_number")

		mandatory_fields = ["driver_id", "amount", "no_of_days", "payment_method"]

		if payment_method == "mpesa":
			mandatory_fields.append("phone_number")

		check_for_empty_values(data, mandatory_fields)

		if payment_method not in ("commission", "mpesa"):
			frappe.local.response["http_status_code"] = 400
			return {"status": "error", "message": "Invalid payment method. Must be 'commission' or 'mpesa'"}

		driver = frappe.db.get_value("Driver", driver_id, "name")

		if not driver:
			frappe.local.response["http_status_code"] = 404
			return {"status": "error", "message": "Driver not found"}

		try:
			amount = float(amount)
			if amount <= 0:
				raise ValueError
		except (TypeError, ValueError):
			frappe.local.response["http_status_code"] = 400
			return {"status": "error", "message": "A valid positive amount is required"}

		try:
			no_of_days = int(no_of_days)
			if no_of_days <= 0:
				raise ValueError
		except (TypeError, ValueError):
			frappe.local.response["http_status_code"] = 400
			return {"status": "error", "message": "A valid positive number of days is required"}

		if payment_method == "commission":
			# Lock the driver's commission ledger rows to prevent race conditions
			frappe.db.sql(
				"SELECT name FROM `tabDriver Commission Ledger` WHERE driver = %s FOR UPDATE",
				driver,
			)

			commission_balance = get_commission_balance_by_driver(driver_id=driver_id)

			if commission_balance["status"] == "error":
				return commission_balance

			if amount > commission_balance["balance"]:
				frappe.local.response["http_status_code"] = 400
				return {"status": "error", "message": "Amount exceeds commission balance"}

		elif payment_method == "mpesa":
			if not validate_phone_number(phone_number):
				frappe.local.response["http_status_code"] = 400
				return {"status": "error", "message": "Invalid phone number"}

			payment_gateway = frappe.get_single("Songa Customization Settings").stk_push_payment_gateway

			if not payment_gateway:
				frappe.local.response["http_status_code"] = 500
				return {
					"status": "error",
					"message": "Please select the payment gateway on Songa Customization Settings",
				}

		try:
			frappe.db.savepoint("recharge_rental_days")

			rental_days = frappe.get_doc(
				{
					"doctype": "Rental Days",
					"company": company or frappe.defaults.get_user_default("company"),
					"posting_date": frappe.utils.nowdate(),
					"driver": driver,
					"no_of_days": no_of_days,
					"amount": amount,
					"transaction_type": "Recharge",
				}
			)
			rental_days.insert()
			rental_days.submit()

			if payment_method == "commission":
				frappe.set_value("Rental Days", rental_days.name, "status", "Completed")

				driver_commission_ledger = frappe.get_doc(
					{
						"doctype": "Driver Commission Ledger",
						"company": company or frappe.defaults.get_user_default("company"),
						"driver": driver,
						"amount": amount,
						"usage": "Rental days recharge",
						"transaction_type": "Deduction",
					}
				)
				driver_commission_ledger.insert()

				deduct_commission(driver_commission_ledger.name, rental_days.name)
				apply_workflow(driver_commission_ledger, "Approve")

			elif payment_method == "mpesa":
				# Rental days have been saved as draft, will be submitted later after payment is confirmed.
				# Use workflow handlers to check payment status and submit rental days
				frappe.set_value("Rental Days", rental_days.name, "status", "In Progress")
				mpesa_express_request = frappe.get_doc(
					{
						"doctype": "Mpesa Express Request",
						"phone_number": phone_number,
						"payment_gateway": payment_gateway,
						"reference_doctype": "Rental Days",
						"reference_name": rental_days.name,
						"transaction_title": "Rental days recharge",
						"transaction_description": f"Rental days recharge for driver {driver_id}, via Mpesa STK Push",
						"currency": "KES",
						"amount": amount,
					}
				)
				mpesa_express_request.insert()
				mpesa_express_request.submit()

				frappe.set_value(
					"Rental Days", rental_days.name, "mpesa_express_request", mpesa_express_request.name
				)

			frappe.db.commit()

		except Exception:
			frappe.db.rollback(save_point="recharge_rental_days")
			raise

		if payment_method == "mpesa":
			# Return early — the balance has not changed yet
			return {
				"status": "pending",
				"message": "M-Pesa payment initiated. Rental days will be recharged once payment is confirmed.",
				"mpesa_request": mpesa_express_request.name,
			}

		total_rental_days_balance = get_rental_days_balance_by_driver(driver_id=driver_id)

		if total_rental_days_balance["status"] == "error":
			return total_rental_days_balance

		return {
			"status": "success",
			"message": "Rental days recharged successfully.",
			"total_rental_days_balance": total_rental_days_balance.get("total_rental_days", 0),
		}

	except Exception as e:
		frappe.local.response["http_status_code"] = 500
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def recharge_kwh():
	try:
		data = check_for_empty_payload()

		if isinstance(data, dict) and data.get("status") == "error":
			return data

		driver_id = data.get("driver_id")
		company = data.get("company")
		amount = data.get("amount")
		kwh = data.get("kwh")
		payment_method = data.get("payment_method")
		phone_number = data.get("phone_number")

		mandatory_fields = ["driver_id", "amount", "kwh"]

		if payment_method == "mpesa":
			mandatory_fields.append("phone_number")

		check_for_empty_values(data, mandatory_fields)

		if payment_method not in ("commission", "mpesa"):
			frappe.local.response["http_status_code"] = 400
			return {"status": "error", "message": "Invalid payment method. Must be 'commission' or 'mpesa'"}

		driver = frappe.db.get_value("Driver", driver_id, "name")

		if not driver:
			frappe.local.response["http_status_code"] = 404
			return {"status": "error", "message": "Driver not found"}

		try:
			amount = float(amount)
			if amount <= 0:
				raise ValueError
		except (TypeError, ValueError):
			frappe.local.response["http_status_code"] = 400
			return {"status": "error", "message": "A valid positive amount is required"}

		try:
			kwh = float(kwh)
			if kwh <= 0:
				raise ValueError
		except (TypeError, ValueError):
			frappe.local.response["http_status_code"] = 400
			return {"status": "error", "message": "A valid positive kWh value is required"}

		if payment_method == "commission":
			# Lock the driver's commission ledger rows to prevent race conditions
			frappe.db.sql(
				"SELECT name FROM `tabDriver Commission Ledger` WHERE driver = %s FOR UPDATE",
				driver,
			)

			commission_balance = get_commission_balance_by_driver(driver_id=driver_id)

			if commission_balance["status"] == "error":
				return commission_balance

			if amount > commission_balance["balance"]:
				frappe.local.response["http_status_code"] = 400
				return {"status": "error", "message": "Amount exceeds commission balance"}

		elif payment_method == "mpesa":
			if not validate_phone_number(phone_number):
				frappe.local.response["http_status_code"] = 400
				return {"status": "error", "message": "Invalid phone number"}

			payment_gateway = frappe.get_single("Songa Customization Settings").stk_push_payment_gateway

			if not payment_gateway:
				frappe.local.response["http_status_code"] = 500
				return {
					"status": "error",
					"message": "Please select the payment gateway on Songa Customization Settings",
				}

		try:
			frappe.db.savepoint("recharge_kwh")

			energy_kwh = frappe.get_doc(
				{
					"doctype": "Energy KWh",
					"company": company or frappe.defaults.get_user_default("company"),
					"posting_date": frappe.utils.nowdate(),
					"driver": driver,
					"energy_qty": kwh,
					"amount": amount,
					"transaction_type": "Recharge",
				}
			)
			energy_kwh.insert()
			energy_kwh.submit()

			if payment_method == "commission":
				frappe.set_value("Energy KWh", energy_kwh.name, "status", "Completed")

				driver_commission_ledger = frappe.get_doc(
					{
						"doctype": "Driver Commission Ledger",
						"company": company or frappe.defaults.get_user_default("company"),
						"driver": driver,
						"amount": amount,
						"usage": "Energy recharge",
						"transaction_type": "Deduction",
					}
				)
				driver_commission_ledger.insert()

				deduct_commission(driver_commission_ledger.name, None, energy_kwh.name)
				apply_workflow(driver_commission_ledger, "Approve")

			elif payment_method == "mpesa":
				frappe.set_value("Energy KWh", energy_kwh.name, "status", "In Progress")
				mpesa_express_request = frappe.get_doc(
					{
						"doctype": "Mpesa Express Request",
						"phone_number": phone_number,
						"payment_gateway": payment_gateway,
						"reference_doctype": "Energy KWh",
						"reference_name": energy_kwh.name,
						"transaction_title": "Energy KWh recharge",
						"transaction_description": f"Energy KWh recharge for driver {driver_id}, via Mpesa STK Push",
						"currency": "KES",
						"amount": amount,
					}
				)
				mpesa_express_request.insert()
				mpesa_express_request.submit()

				frappe.set_value(
					"Energy KWh", energy_kwh.name, "mpesa_express_request", mpesa_express_request.name
				)

			frappe.db.commit()

		except Exception:
			frappe.db.rollback(save_point="recharge_kwh")
			raise

		if payment_method == "mpesa":
			# Retuen early - the balance has not changed yet
			return {
				"status": "pending",
				"message": "M-Pesa payment initiated. Energy KWh will be recharged once payment is confirmed.",
				"mpesa_request": mpesa_express_request.name,
			}

		kwh_balance = get_energy_kwh_balance_by_driver(driver_id=driver_id)

		if kwh_balance["status"] == "error":
			return kwh_balance

		return {
			"status": "success",
			"message": "kWh recharged successfully.",
			"kwh_balance": kwh_balance.get("total_kwh", 0),
		}

	except Exception as e:
		frappe.local.response["http_status_code"] = 500
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def consume_rental_days():
	try:
		data = check_for_empty_payload()

		if isinstance(data, dict) and data.get("status") == "error":
			return data

		driver_id = data.get("driver_id")
		no_of_days = data.get("no_of_days")
		company = data.get("company")

		check_for_empty_values(data, ["driver_id", "no_of_days"])

		driver = frappe.db.get_value("Driver", driver_id, "name")

		if not driver:
			frappe.local.response["http_status_code"] = 404
			return {"status": "error", "message": "Driver not found"}

		try:
			no_of_days = int(no_of_days)
			if no_of_days <= 0:
				raise ValueError
		except (TypeError, ValueError):
			frappe.local.response["http_status_code"] = 400
			return {"status": "error", "message": "A valid positive number of days is required"}

		frappe.db.sql(
			"SELECT name FROM `tabRental Days` WHERE driver = %s FOR UPDATE",
			driver,
		)

		rental_days_balance = get_rental_days_balance_by_driver(driver_id=driver_id)

		if rental_days_balance["status"] == "error":
			return rental_days_balance

		rental_days_balance = rental_days_balance.get("total_rental_days", 0)

		if no_of_days > rental_days_balance:
			frappe.local.response["http_status_code"] = 400
			return {"status": "error", "message": "Not enough rental days balance"}

		rental_days = frappe.get_doc(
			{
				"doctype": "Rental Days",
				"company": company or frappe.defaults.get_user_default("company"),
				"posting_date": frappe.utils.nowdate(),
				"driver": driver,
				"no_of_days": no_of_days,
				"status": "Completed",
				"transaction_type": "Usage",
			}
		)
		rental_days.insert()
		rental_days.submit()
		frappe.db.commit()

		actual_balance = get_rental_days_balance_by_driver(driver_id=driver_id)

		if actual_balance["status"] == "error":
			return actual_balance

		return {
			"status": "success",
			"message": "Rental days consumed successfully.",
			"total_rental_days_balance": actual_balance.get("total_rental_days", 0),
		}

	except Exception as e:
		frappe.local.response["http_status_code"] = 500
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def consume_kwh():
	try:
		data = check_for_empty_payload()

		if isinstance(data, dict) and data.get("status") == "error":
			return data

		driver_id = data.get("driver_id")
		kwh = data.get("kwh")
		company = data.get("company")

		check_for_empty_values(data, ["driver_id", "kwh"])

		driver = frappe.db.get_value("Driver", driver_id, "name")

		if not driver:
			frappe.local.response["http_status_code"] = 404
			return {"status": "error", "message": "Driver not found"}

		try:
			kwh = float(kwh)
			if kwh <= 0:
				raise ValueError
		except (TypeError, ValueError):
			frappe.local.response["http_status_code"] = 400
			return {"status": "error", "message": "A valid positive kWh value is required"}

		frappe.db.sql(
			"SELECT name FROM `tabEnergy KWh` WHERE driver = %s FOR UPDATE",
			driver,
		)

		kwh_balance = get_energy_kwh_balance_by_driver(driver_id=driver_id)

		if kwh_balance["status"] == "error":
			return kwh_balance

		kwh_balance = kwh_balance.get("total_kwh", 0)

		if kwh > kwh_balance:
			frappe.local.response["http_status_code"] = 400
			return {"status": "error", "message": "Not enough kWh balance"}

		energy_kwh = frappe.get_doc(
			{
				"doctype": "Energy KWh",
				"company": company or frappe.defaults.get_user_default("company"),
				"posting_date": frappe.utils.nowdate(),
				"driver": driver,
				"energy_qty": kwh,
				"status": "Completed",
				"transaction_type": "Usage",
			}
		)
		energy_kwh.insert()
		energy_kwh.submit()
		frappe.db.commit()

		actual_balance = get_energy_kwh_balance_by_driver(driver_id=driver_id)

		if actual_balance["status"] == "error":
			return actual_balance

		return {
			"status": "success",
			"message": "kWh consumed successfully.",
			"kwh_balance": actual_balance.get("total_kwh", 0),
		}

	except Exception as e:
		frappe.local.response["http_status_code"] = 500
		return {"status": "error", "message": str(e)}


def _cancel_document(doctype, document_id, id_field):
	if not frappe.db.exists(doctype, document_id):
		frappe.local.response["http_status_code"] = 404
		return {"status": "error", "message": f"{doctype} not found"}

	doc = frappe.get_doc(doctype, document_id)

	if doc.docstatus == 0:
		frappe.local.response["http_status_code"] = 400
		return {"status": "error", "message": f"{doctype} is not submitted"}

	if doc.docstatus == 2:
		frappe.local.response["http_status_code"] = 200
		return {"status": "success", "message": f"{doctype} is already cancelled. ID: {document_id}"}

	savepoint = f"cancel_{id_field}"
	frappe.db.savepoint(savepoint)

	try:
		doc.flags.ignore_links = True
		doc.cancel()

		if doc.driver_commission_ledger:
			driver_commission_ledger = frappe.get_doc(
				"Driver Commission Ledger", doc.driver_commission_ledger
			)
			journal_entry = frappe.get_doc("Journal Entry", driver_commission_ledger.journal_entry)

			apply_workflow(driver_commission_ledger, "Cancel")
			journal_entry.flags.ignore_links = True
			journal_entry.cancel()
		elif doc.mpesa_express_request:
			mpesa_express_request = frappe.get_doc("Mpesa Express Request", doc.mpesa_express_request)
			mpesa_express_request.flags.ignore_links = True
			mpesa_express_request.cancel()

	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise

	frappe.db.commit()

	return {"status": "success", "message": f"{doctype} cancelled successfully. ID: {document_id}"}


@frappe.whitelist(allow_guest=False)
def cancel_rental_days():
	try:
		data = check_for_empty_payload()

		if isinstance(data, dict) and data.get("status") == "error":
			return data

		check_for_empty_values(data, ["rental_day_id"])

		return _cancel_document("Rental Days", data.get("rental_day_id"), "rental_day_id")

	except frappe.PermissionError:
		frappe.local.response["http_status_code"] = 403
		return {"status": "error", "message": "You do not have permission to cancel this record"}
	except Exception as e:
		frappe.db.rollback()
		frappe.local.response["http_status_code"] = 500
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def cancel_energy_kwh():
	try:
		data = check_for_empty_payload()

		if isinstance(data, dict) and data.get("status") == "error":
			return data

		check_for_empty_values(data, ["energy_kwh_id"])

		return _cancel_document("Energy KWh", data.get("energy_kwh_id"), "energy_kwh_id")

	except frappe.PermissionError:
		frappe.local.response["http_status_code"] = 403
		return {"status": "error", "message": "You do not have permission to cancel this record"}
	except Exception as e:
		frappe.db.rollback()
		frappe.local.response["http_status_code"] = 500
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def create_asset_repair():
    try:
        data = check_for_empty_payload()
        if isinstance(data, dict) and data.get("status") == "error":
            return data

        check_for_empty_values(data, ["asset_repair_id", "failure_date", "description", "asset_id", "asset_type_id", "user_email"])

        asset_repair_id = data.get("asset_repair_id")
        user_email = data.get("user_email")
        description = data.get("description")
        asset_id = data.get("asset_id")
        asset_type_id = data.get("asset_type_id")
        failure_date = data.get("failure_date")
        company = data.get("company")

        if not frappe.db.exists("User", user_email):
            frappe.local.response["http_status_code"] = 404
            return {"status": "error", "message": "User not found"}

        if frappe.db.exists("Asset Repair", {"custom_asset_repair_id": asset_repair_id}):
            frappe.local.response["http_status_code"] = 200
            return {
                "status": "success",
                "message": "Duplicate Asset Repair",
                "asset_repair_id": asset_repair_id,
            }

        savepoint = "create_asset_repair"
        frappe.db.savepoint(savepoint)

        try:
            # setting the user_email here, so its easy to identify who created the asset repair and will need updates
            frappe.set_user(user_email)

            asset_repair = frappe.new_doc("Asset Repair")
            asset_repair.company = company or frappe.defaults.get_user_default("company")
            asset_repair.custom_asset_repair_id = asset_repair_id
            asset_repair.asset = asset_id
            asset_repair.custom_asset_type_id = asset_type_id
            asset_repair.description = description
            asset_repair.failure_date = frappe.utils.getdate(failure_date)
            asset_repair.insert(ignore_permissions=True)

            apply_workflow(asset_repair, "Send for Approval HM")

            frappe.db.commit()

            return {
                "status": "success",
                "message": "Asset Repair created successfully.",
                "asset_repair_id": asset_repair.custom_asset_repair_id,
            }

        except Exception:
            frappe.db.rollback(save_point=savepoint)
            raise

    except Exception as e:
        frappe.local.response["http_status_code"] = 500
        return {"status": "error", "message": str(e)}

    finally:
        frappe.set_user("Administrator")


@frappe.whitelist(allow_guest=False)
def check_asset_repair_status():
	try:
		data = check_for_empty_payload()

		if isinstance(data, dict) and data.get("status") == "error":
			return data

		check_for_empty_values(data, ["asset_repair_id"])

		asset_repair_id = data.get("asset_repair_id")

		if not frappe.db.exists("Asset Repair", {"custom_asset_repair_id": asset_repair_id}):
			frappe.local.response["http_status_code"] = 404
			return {"status": "error", "message": f"Asset Repair not found. ID: {asset_repair_id}"}

		asset_repair = frappe.get_doc("Asset Repair", { "custom_asset_repair_id": asset_repair_id })

		message = {
			"asset_repair_id": asset_repair.custom_asset_repair_id,
			"asset": asset_repair.asset,
			"asset_name": asset_repair.asset_name,
			"asset_type": asset_repair.custom_asset_type,
			"failure_date": asset_repair.failure_date,
			"completion_date": asset_repair.completion_date,
			"repair_status": asset_repair.repair_status,
			"workflow_state": asset_repair.workflow_state,
			"stock_consumption": asset_repair.stock_consumption,
			"total_repair_cost": asset_repair.total_repair_cost,
			"description": asset_repair.description,
			"actions_performed": asset_repair.actions_performed,
		}

		if asset_repair.stock_consumption:
			message["stock_items"] = [
				{
					"item_code": item.item_code,
					"warehouse": item.warehouse,
					"valuation_rate": item.valuation_rate,
					"consumed_quantity": item.consumed_quantity,
					"total_value": item.total_value,
				}
				for item in asset_repair.stock_items
			]

		return {"status": "success", "message": message}
	except Exception as e:
		frappe.local.response["http_status_code"] = 500
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def comment_on_asset_repair():
	try:
		data = check_for_empty_payload()

		if isinstance(data, dict) and data.get("status") == "error":
			return data

		check_for_empty_values(data, ["asset_repair_id", "comment", "user_email"])

		asset_repair_id = data.get("asset_repair_id")
		user_email = data.get("user_email")
		comment = data.get("comment")

		if not frappe.db.exists("User", user_email):
			frappe.local.response["http_status_code"] = 404
			return {"status": "error", "message": "User not found"}

		if not frappe.db.exists("Asset Repair", {"custom_asset_repair_id": asset_repair_id}):
			frappe.local.response["http_status_code"] = 404
			return {"status": "error", "message": "Asset Repair not found"}

		frappe.set_user(user_email)

		reference_name = frappe.db.get_value("Asset Repair", {"custom_asset_repair_id": asset_repair_id}, "name")

		doc = frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Comment",
				"reference_doctype": "Asset Repair",
				"reference_name": reference_name,
				"content": comment,
				"published": 1,
			}
		)
		doc.insert(ignore_permissions=True)

		return {"status": "success", "message": "Comment added successfully."}
	except Exception as e:
		frappe.local.response["http_status_code"] = 500
		return {"status": "error", "message": str(e)}
	finally:
		frappe.set_user("Administrator")
