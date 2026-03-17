import json

import frappe


def get_expense_and_liability_accounts():
	try:
		settings = frappe.get_single("Songa Customization Settings")
		expense_account = settings.expense_account
		liability_account = settings.liability_account

		if not expense_account or not liability_account:
			frappe.throw("Expense and Liability accounts must be set in Songa Customization Settings")

		return expense_account, liability_account
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Accounts Error")
		frappe.throw(str(e))


@frappe.whitelist(allow_guest=False)
def allocate_commission(driver_commission_ledger_name):
	try:
		driver_commission_ledger = frappe.get_doc("Driver Commission Ledger", driver_commission_ledger_name)
		driver = driver_commission_ledger.driver
		supplier = frappe.db.get_value("Driver", driver, "transporter")
		amount = driver_commission_ledger.amount

		if not frappe.db.exists("Driver", driver_commission_ledger.driver):
			frappe.throw("Driver not found")

		if not supplier:
			frappe.throw("Driver does not have an associated supplier")

		if amount <= 0:
			frappe.throw("Amount must be greater than zero for allocation")

		expense_account, liability_account = get_expense_and_liability_accounts()

		journal_entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"posting_date": frappe.utils.nowdate(),
				"voucher_type": "Journal Entry",
				"company": driver_commission_ledger.company,
				"user_remark": f"Commission allocation for driver {driver_commission_ledger.driver_name} - Driver Commission Ledger {driver_commission_ledger.name}",
				"accounts": [
					{
						"account": liability_account,
						"party_type": "Supplier",
						"party": supplier,
						"debit_in_account_currency": 0,
						"credit_in_account_currency": amount,
						"is_advance": "No",
					},
					{
						"account": expense_account,
						"debit_in_account_currency": amount,
						"credit_in_account_currency": 0,
						"is_advance": "No",
					},
				],
			}
		)

		try:
			frappe.db.savepoint("allocate_commission")
			journal_entry.insert()
			journal_entry.submit()
			frappe.set_value(
				"Driver Commission Ledger", driver_commission_ledger_name, "journal_entry", journal_entry.name
			)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback(save_point="allocate_commission")
			raise

		return {
			"status": "success",
			"message": "Commission allocated successfully.",
			"data": journal_entry.name,
		}
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Commission Allocation Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def deduct_commission(driver_commission_ledger_name, rental_days_record_name=None, KWh_record_name=None):
	try:
		driver_commission_ledger = frappe.get_doc("Driver Commission Ledger", driver_commission_ledger_name)
		driver = driver_commission_ledger.driver
		supplier = frappe.db.get_value("Driver", driver, "transporter")
		amount = driver_commission_ledger.amount

		if not frappe.db.exists("Driver", driver_commission_ledger.driver):
			frappe.throw("Driver not found")

		if not supplier:
			frappe.throw("Driver does not have an associated supplier")

		if amount <= 0:
			frappe.throw("Amount must be greater than zero for deduction")

		# Lock commission ledger rows for this driver to prevent race conditions
		# when deduct_commission is called directly as a whitelisted endpoint
		frappe.db.sql(
			"SELECT name FROM `tabDriver Commission Ledger` WHERE driver = %s FOR UPDATE",
			driver,
		)

		commission_balance = get_commission_balance_by_driver(driver_id=driver)

		if commission_balance["status"] == "error":
			return commission_balance

		if commission_balance["balance"] < amount:
			frappe.throw(
				f"Insufficient commission balance. Available balance: {commission_balance['balance']}"
			)

		expense_account, liability_account = get_expense_and_liability_accounts()

		journal_entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"posting_date": frappe.utils.nowdate(),
				"voucher_type": "Journal Entry",
				"company": driver_commission_ledger.company,
				"user_remark": f"Commission deduction for driver {driver_commission_ledger.driver} - Driver Commission Ledger {driver_commission_ledger.name}",
				"accounts": [
					{
						"account": liability_account,
						"party_type": "Supplier",
						"party": supplier,
						"debit_in_account_currency": amount,
						"credit_in_account_currency": 0,
						"is_advance": "No",
					},
					{
						"account": expense_account,
						"debit_in_account_currency": 0,
						"credit_in_account_currency": amount,
						"is_advance": "No",
					},
				],
			}
		)

		try:
			frappe.db.savepoint("deduct_commission")
			journal_entry.insert()
			journal_entry.submit()
			frappe.set_value(
				"Driver Commission Ledger", driver_commission_ledger_name, "journal_entry", journal_entry.name
			)

			if rental_days_record_name:
				frappe.db.set_value(
					"Rental Days",
					rental_days_record_name,
					"driver_commission_ledger",
					driver_commission_ledger_name,
				)
			elif KWh_record_name:
				frappe.db.set_value(
					"Energy KWh", KWh_record_name, "driver_commission_ledger", driver_commission_ledger_name
				)

			frappe.db.commit()
		except Exception:
			frappe.db.rollback(save_point="deduct_commission")
			raise

		return {"status": "success", "message": "Commission deducted successfully."}
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Commission Deduction Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def get_commission_balance_by_driver(driver_id=None):
	try:
		if not driver_id and frappe.request.data:
			driver_id = json.loads(frappe.request.data).get("driver_id")

		if not driver_id:
			frappe.throw("driver_id is required")

		if not frappe.db.exists("Driver", driver_id):
			frappe.throw("Driver not found")

		supplier = frappe.db.get_value("Driver", driver_id, "transporter")

		if not supplier:
			frappe.throw("Driver does not have an associated supplier")

		expense_account, _ = get_expense_and_liability_accounts()

		balance = frappe.get_list(
			"GL Entry",
			filters={"against": supplier, "account": expense_account},
			fields=["sum(debit) - sum(credit) as balance"],
		)

		return {"status": "success", "balance": balance[0].balance or 0}
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Commission Balance Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def get_rental_days_balance_by_driver(driver_id=None):
	try:
		if not driver_id and frappe.request.data:
			driver_id = json.loads(frappe.request.data).get("driver_id")

		if not driver_id:
			frappe.throw("driver_id is required")

		if not frappe.db.exists("Driver", driver_id):
			frappe.throw("Driver not found")

		recharged_rental_days = (
			frappe.get_value(
				"Rental Days",
				{"driver": driver_id, "docstatus": 1, "transaction_type": "Recharge"},
				"sum(no_of_days)",
			)
			or 0
		)

		used_rental_days = (
			frappe.get_value(
				"Rental Days",
				{"driver": driver_id, "docstatus": 1, "transaction_type": "Usage"},
				"sum(no_of_days)",
			)
			or 0
		)

		rental_days_balance = recharged_rental_days - used_rental_days

		return {"status": "success", "total_rental_days": rental_days_balance or 0}

	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Rental Days Balance Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def get_energy_kwh_balance_by_driver(driver_id=None):
	try:
		if not driver_id and frappe.request.data:
			driver_id = json.loads(frappe.request.data).get("driver_id")

		if not driver_id:
			frappe.throw("driver_id is required")

		if not frappe.db.exists("Driver", driver_id):
			frappe.throw("Driver not found")

		recharged_kwh = (
			frappe.get_value(
				"Energy KWh",
				{"driver": driver_id, "docstatus": 1, "transaction_type": "Recharge"},
				"sum(energy_qty)",
			)
			or 0
		)

		used_kwh = (
			frappe.get_value(
				"Energy KWh",
				{"driver": driver_id, "docstatus": 1, "transaction_type": "Usage"},
				"sum(energy_qty)",
			)
			or 0
		)

		total_kwh_balance = recharged_kwh - used_kwh

		return {"status": "success", "total_kwh": total_kwh_balance or 0}

	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Energy KWh Balance Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def get_overall_balance(driver_id=None):
	try:
		# Changed to driver_id=None so the request.data fallback can actually trigger
		if not driver_id and frappe.request.data:
			driver_id = json.loads(frappe.request.data).get("driver_id")

		if not driver_id:
			frappe.throw("driver_id is required")

		commission_balance = get_commission_balance_by_driver(driver_id)
		rental_days_balance = get_rental_days_balance_by_driver(driver_id)
		energy_kwh_balance = get_energy_kwh_balance_by_driver(driver_id)

		if commission_balance["status"] == "error":
			return {
				"status": "error",
				"message": f"Error fetching commission balance: {commission_balance['message']}",
			}

		if rental_days_balance["status"] == "error":
			return {
				"status": "error",
				"message": f"Error fetching rental days balance: {rental_days_balance['message']}",
			}

		if energy_kwh_balance["status"] == "error":
			return {
				"status": "error",
				"message": f"Error fetching energy kWh balance: {energy_kwh_balance['message']}",
			}

		return {
			"status": "success",
			"data": {
				"commission_balance": commission_balance["balance"],
				"rental_days_balance": rental_days_balance["total_rental_days"],
				"energy_kwh_balance": energy_kwh_balance["total_kwh"],
			},
		}

	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Overall Balance Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def process_mpesa_express_request(doc):
	try:
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
