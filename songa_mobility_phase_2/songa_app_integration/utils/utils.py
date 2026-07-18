import json

import frappe
import requests
from erpnext.accounts.party import get_party_account

from songa_mobility_phase_2.songa_app_integration.report_helpers import (
	get_commission_balance,
	get_energy_kwh_balance,
	get_rental_days_balance,
)


def get_driver_commission_account():
	try:
		settings = frappe.get_single("Songa Customization Settings")
		driver_commission_account = settings.driver_commission_account

		if not driver_commission_account:
			frappe.throw("Driver Commission account must be set in Songa Customization Settings")

		return driver_commission_account
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Accounts Error")
		frappe.throw(str(e))


def get_supplier_party_account(supplier, company):
	try:
		if not supplier or not company:
			frappe.throw("Both supplier and company are needed to get supplier's party account")

		return get_party_account("Supplier", supplier, company)
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Accounts Error")
		frappe.throw(str(e))


def get_commission_deduction_accounts(rental_days_record_name=None, KWh_record_name=None):
	"""Return debit/credit accounts for a commission deduction based on recharge type."""
	settings = frappe.get_single("Songa Customization Settings")

	if rental_days_record_name:
		debit_account = settings.rental_recharge_commission_debit
		credit_account = settings.rental_recharge_commission_credit
		if not debit_account or not credit_account:
			frappe.throw(
				"Please set Rental Recharge Commission Debit and Credit accounts on Songa Customization Settings"
			)
		return debit_account, credit_account

	if KWh_record_name:
		debit_account = settings.battery_swap_commission_debit
		credit_account = settings.battery_swap_commission_credit
		if not debit_account or not credit_account:
			frappe.throw(
				"Please set Battery Swap Commission Debit and Credit accounts on Songa Customization Settings"
			)
		return debit_account, credit_account

	frappe.throw(
		"Cannot determine commission deduction accounts. A Rental Days or Energy KWh record is required."
	)


def _get_driver_id(driver_id):
	# direct function calls - driver_id as argument
	if driver_id:
		return driver_id

	# internall calls - frappe.call
	if frappe.form_dict.get("driver_id"):
		return frappe.form_dict.get("driver_id")

	# api calls - JSON body
	if frappe.request and frappe.request.data:
		try:
			return json.loads(frappe.request.data).get("driver_id")
		except (json.JSONDecodeError, AttributeError):
			pass

	return None


def _get_company(company):
	# direct function calls - company as argument
	if company:
		return company
	# internall calls - frappe.call
	if frappe.form_dict.get("company"):
		return frappe.form_dict.get("company")
	# api calls - JSON body
	if frappe.request and frappe.request.data:
		try:
			company = json.loads(frappe.request.data).get("company")
			if company:
				return company
		except (json.JSONDecodeError, AttributeError):
			pass
	return frappe.defaults.get_user_default("company")


def reconcile_payments(driver_id):
	try:
		if not driver_id:
			frappe.throw("driver_id is required")
		if not frappe.db.exists("Driver", driver_id):
			frappe.throw("Driver not found")
		supplier = frappe.db.get_value("Driver", driver_id, "transporter")
		if not supplier:
			frappe.throw("Driver does not have an associated supplier")

		company = frappe.defaults.get_user_default("company")

		if not company:
			frappe.throw("Default company is not set for current user")

		reconcile_doc = frappe.new_doc("Payment Reconciliation")
		reconcile_doc.party_type = "Supplier"
		reconcile_doc.party = supplier
		reconcile_doc.company = company
		reconcile_doc.receivable_payable_account = get_supplier_party_account(
			supplier=supplier, company=company
		)

		reconcile_doc.get_unreconciled_entries()

		if not reconcile_doc.invoices or not reconcile_doc.payments:
			frappe.log_error("No invoices or payments found for driver", "Reconcile Payments Error")
			return {
				"status": "error",
				"message": "No invoices or payments found for driver",
			}

		args = {
			"invoices": [invoice.as_dict() for invoice in reconcile_doc.invoices],
			"payments": [payment.as_dict() for payment in reconcile_doc.payments],
		}

		if not args["invoices"] or not args["payments"]:
			frappe.log_error("No invoices or payments found for driver", "Reconcile Payments Error")
			return {
				"status": "error",
				"message": "No invoices or payments found for driver",
			}

		reconcile_doc.allocate_entries(args)
		reconcile_doc.reconcile()
		frappe.db.commit()
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Reconcile Payments Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def allocate_commission(driver_commission_ledger_name, commit=True):
	try:
		driver_commission_ledger = frappe.get_doc("Driver Commission Ledger", driver_commission_ledger_name)
		driver = driver_commission_ledger.driver
		supplier = frappe.db.get_value("Driver", driver, "transporter")
		amount = driver_commission_ledger.amount
		company = driver_commission_ledger.company

		if not frappe.db.exists("Driver", driver_commission_ledger.driver):
			frappe.throw("Driver not found")

		if not supplier:
			frappe.throw("Driver does not have an associated supplier")

		if amount <= 0:
			frappe.throw("Amount must be greater than zero for allocation")

		expense_account, liability_account = (
			get_driver_commission_account(),
			get_supplier_party_account(supplier=supplier, company=company),
		)

		branch_and_cost_center_dict = get_branch_and_cost_center_by_supplier(supplier=supplier)
		branch = branch_and_cost_center_dict.get("branch", "")
		cost_center = branch_and_cost_center_dict.get("cost_center", "")

		branch_cost_center_fields = {
			**({"branch": branch} if branch else {}),
			**({"cost_center": cost_center} if cost_center else {}),
		}

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
						**branch_cost_center_fields,
						"is_advance": "No",
					},
					{
						"account": expense_account,
						"debit_in_account_currency": amount,
						**branch_cost_center_fields,
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
				"Driver Commission Ledger",
				driver_commission_ledger_name,
				"journal_entry",
				journal_entry.name,
			)
			if commit:
				frappe.db.commit()
		except Exception:
			frappe.db.rollback(save_point="allocate_commission")
			raise

		return {
			"status": "success",
			"message": "Commission allocated successfully.",
			"data": journal_entry.name,
		}

		reconcile_payments(driver_id=driver)
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Commission Allocation Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def deduct_commission(
	driver_commission_ledger_name,
	rental_days_record_name=None,
	KWh_record_name=None,
	commit=True,
):
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

		if not rental_days_record_name:
			rental_days_record_name = frappe.db.get_value(
				"Rental Days",
				{"driver_commission_ledger": driver_commission_ledger_name},
				"name",
			)
		if not KWh_record_name:
			KWh_record_name = frappe.db.get_value(
				"Energy KWh",
				{"driver_commission_ledger": driver_commission_ledger_name},
				"name",
			)

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

		debit_account, credit_account = get_commission_deduction_accounts(
			rental_days_record_name=rental_days_record_name,
			KWh_record_name=KWh_record_name,
		)

		branch_and_cost_center_dict = get_branch_and_cost_center_by_supplier(supplier=supplier)
		branch = branch_and_cost_center_dict.get("branch", "")
		cost_center = branch_and_cost_center_dict.get("cost_center", "")

		branch_cost_center_fields = {
			**({"branch": branch} if branch else {}),
			**({"cost_center": cost_center} if cost_center else {}),
		}

		journal_entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"posting_date": frappe.utils.nowdate(),
				"voucher_type": "Journal Entry",
				"company": driver_commission_ledger.company,
				"user_remark": f"Commission deduction for driver {driver_commission_ledger.driver} - Driver Commission Ledger {driver_commission_ledger.name}",
				"accounts": [
					{
						"account": debit_account,
						"debit_in_account_currency": amount,
						"party_type": "Supplier",
						"party": supplier,
						**branch_cost_center_fields,
						"credit_in_account_currency": 0,
						"is_advance": "No",
					},
					{
						"account": credit_account,
						"debit_in_account_currency": 0,
						"credit_in_account_currency": amount,
						**branch_cost_center_fields,
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
				"Driver Commission Ledger",
				driver_commission_ledger_name,
				"journal_entry",
				journal_entry.name,
			)

			if rental_days_record_name:
				frappe.db.set_value(
					"Rental Days",
					rental_days_record_name,
					{
						"driver_commission_ledger": driver_commission_ledger_name,
						"status": "Completed",
					},
				)
			elif KWh_record_name:
				frappe.db.set_value(
					"Energy KWh",
					KWh_record_name,
					{
						"driver_commission_ledger": driver_commission_ledger_name,
						"status": "Completed",
					},
				)

			if commit:
				frappe.db.commit()

			reconcile_payments(driver_id=driver)
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
def get_commission_balance_by_driver(driver_id=None, company=None):
	"""Returns the commission payable for a driver"""
	try:
		driver_id = _get_driver_id(driver_id)

		if not driver_id:
			frappe.throw("driver_id is required")

		company = _get_company(company)

		if not company:
			frappe.throw("company is required")

		if not frappe.db.exists("Driver", driver_id):
			frappe.throw("Driver not found")

		supplier = frappe.db.get_value("Driver", driver_id, "transporter")

		if not supplier:
			frappe.throw("Driver does not have an associated supplier")

		balance = get_commission_balance(supplier, company)

		return {"status": "success", "balance": balance}
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Commission Balance Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def get_rental_days_balance_by_driver(driver_id=None):
	try:
		driver_id = _get_driver_id(driver_id)

		if not driver_id:
			frappe.throw("driver_id is required")

		if not frappe.db.exists("Driver", driver_id):
			frappe.throw("Driver not found")

		rental_days_balance = get_rental_days_balance(driver_id)

		return {"status": "success", "total_rental_days": rental_days_balance or 0}

	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Rental Days Balance Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def get_energy_kwh_balance_by_driver(driver_id=None):
	try:
		driver_id = _get_driver_id(driver_id)

		if not driver_id:
			frappe.throw("driver_id is required")

		if not frappe.db.exists("Driver", driver_id):
			frappe.throw("Driver not found")

		total_kwh_balance = get_energy_kwh_balance(driver_id)

		return {"status": "success", "total_kwh": total_kwh_balance or 0}

	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Energy KWh Balance Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def get_overall_balance(driver_id=None):
	try:
		driver_id = _get_driver_id(driver_id)

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
		if reference_doc.status == doc.status:
			return

		try:
			frappe.db.savepoint("mpesa_express_request")

			frappe.set_value(reference_doctype, doc.reference_name, "status", doc.status)

			frappe.db.commit()

		except Exception:
			frappe.db.rollback(save_point="mpesa_express_request")
			raise

		url = frappe.get_single("Songa Customization Settings").songa_webhook_endpoint

		if not url:
			frappe.log_error(
				"Songa webhook endpoint not found, please check Songa Customization Settings",
				"Commission Ledger Workflow",
			)
			return

		# initiate logger
		frappe.utils.logger.set_log_level("INFO")
		songa_webhook_logger = frappe.logger("songa_webhook_log", allow_site=True, file_count=20)

		return_payload = {
			"driver_id": reference_doc.driver,
			"transaction_type": reference_doc.transaction_type,
			"amount": reference_doc.amount,
			"mpesa_express_request": doc.name,
		}

		headers = {"Content-Type": "application/json"}

		if doc.status == "Completed":
			if reference_doctype == "Rental Days":
				return_payload["action_type"] = "Rental days recharge"
				return_payload["rental_days_balance"] = get_rental_days_balance_by_driver(
					driver_id=reference_doc.driver
				)
			elif reference_doctype == "Energy KWh":
				return_payload["action_type"] = "Energy recharge"
				return_payload["energy_kwh_balance"] = get_energy_kwh_balance_by_driver(
					driver_id=reference_doc.driver
				)

			data = json.dumps(return_payload)
			response = requests.post(url, data=data, headers=headers, verify=True)
			if response.status_code != 200:
				frappe.log_error(f"{response}", "Error sending data to webhook endpoint")
				return
			songa_webhook_logger.info(f"Mpesa Express Request: {doc.name}. Response: {response}\n")
		else:
			frappe.logger().info(
				f"{reference_doctype} recharge cancelled for driver {reference_doc.driver} "
				f"due to failed M-Pesa payment."
			)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Mpesa Express Request Workflow Error")
		frappe.throw(str(e))


@frappe.whitelist(allow_guest=False)
def get_linked_supplier(customer):
	"""Returns the supplier linked to a customer via Party Link doctype"""
	try:
		if not customer:
			frappe.throw("Customer is required to get linked supplier")

		# Check for linked supplier where Customer is either secondary or primary party
		linked_supplier = frappe.db.get_value(
			"Party Link",
			{"secondary_role": "Customer", "secondary_party": customer},
			"primary_party",
		) or frappe.db.get_value(
			"Party Link",
			{"primary_role": "Customer", "primary_party": customer},
			"secondary_party",
		)

		return linked_supplier

	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Linked Supplier Error")
		frappe.throw(str(e))


@frappe.whitelist(allow_guest=False)
def get_branch_and_cost_center_by_supplier(supplier):
	try:
		if not supplier:
			frappe.throw("Supplier is required to get branch and cost center")

		branch = frappe.db.get_value("Supplier", supplier, "custom_branch")
		cost_center = frappe.db.get_value("Supplier", supplier, "custom_cost_center")

		return {"branch": branch, "cost_center": cost_center}

	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Branch and Cost Center Error")
		frappe.throw(str(e))
