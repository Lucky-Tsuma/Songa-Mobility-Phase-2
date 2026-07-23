import json

import frappe
from erpnext.accounts.party import get_party_account

from songa_mobility_phase_2.songa_app_integration.report_helpers import (
	get_commission_balance,
	get_energy_kwh_balance,
	get_rental_days_balance,
)
from songa_mobility_phase_2.songa_app_integration.utils.songa_webhook import send_songa_webhook


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

		if driver_commission_ledger.transaction_type != "Allocation":
			frappe.throw("Commission allocation is only supported for Allocation ledgers.")

		if driver_commission_ledger.journal_entry:
			return {
				"status": "success",
				"message": "Commission already allocated.",
				"data": driver_commission_ledger.journal_entry,
			}

		if driver_commission_ledger.workflow_state != "Approved":
			frappe.throw(
				"Driver Commission Ledger must be Approved before posting the allocation Journal Entry."
			)

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

		reconcile_payments(driver_id=driver)

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


MAX_MPESA_WALLET_ATTEMPTS = 5
MPESA_WALLET_RETRY_INTERVAL_MINUTES = 5

MPESA_WALLET_ACCOUNT_FIELDS = {
	"Energy KWh": ("battery_swap_mpesa_debit", "battery_swap_mpesa_credit"),
	"Rental Days": ("rental_recharge_mpesa_debit", "rental_recharge_mpesa_credit"),
}


def _mpesa_wallet_action_type(reference_doctype):
	if reference_doctype == "Rental Days":
		return "Rental days recharge"
	if reference_doctype == "Energy KWh":
		return "Energy recharge"
	return None


def get_mpesa_wallet_accounts(reference_doctype):
	"""Return debit/credit accounts for an M-Pesa wallet recharge Journal Entry."""
	fields = MPESA_WALLET_ACCOUNT_FIELDS.get(reference_doctype)
	if not fields:
		frappe.throw(f"Unsupported M-Pesa wallet reference doctype: {reference_doctype}")

	settings = frappe.get_single("Songa Customization Settings")
	debit_account = settings.get(fields[0])
	credit_account = settings.get(fields[1])
	missing = [frappe.unscrub(field) for field in fields if not settings.get(field)]
	if missing:
		frappe.throw(
			"Please set the following accounts on Songa Customization Settings: " + ", ".join(missing)
		)

	return debit_account, credit_account


def post_mpesa_wallet_journal_entry(payment_doc, reference_doc):
	"""
	Create and submit the Songa wallet Journal Entry for a completed M-Pesa payment.

	Supports Mpesa Express Request and Mpesa C2B Payment Register sources.
	Idempotent: returns an existing linked JE if custom_songa_journal_entry is already set.
	"""
	source_doctype = payment_doc.doctype
	if source_doctype not in ("Mpesa Express Request", "Mpesa C2B Payment Register"):
		frappe.throw(f"Unsupported M-Pesa payment source: {source_doctype}")

	existing_je = getattr(payment_doc, "custom_songa_journal_entry", None) or frappe.db.get_value(
		source_doctype,
		payment_doc.name,
		"custom_songa_journal_entry",
	)
	if existing_je:
		return existing_je

	if source_doctype == "Mpesa Express Request" and payment_doc.status != "Completed":
		frappe.throw("M-Pesa wallet Journal Entry can only be posted for Completed requests.")

	reference_doctype = reference_doc.doctype
	if reference_doctype not in MPESA_WALLET_ACCOUNT_FIELDS:
		frappe.throw(f"Unsupported M-Pesa wallet reference doctype: {reference_doctype}")

	driver = reference_doc.driver
	if not driver or not frappe.db.exists("Driver", driver):
		frappe.throw("Driver not found on the M-Pesa reference document.")

	supplier = frappe.db.get_value("Driver", driver, "transporter")
	if not supplier:
		frappe.throw("Driver does not have an associated supplier")

	amount = reference_doc.amount
	if not amount or amount <= 0:
		frappe.throw("Amount must be greater than zero for M-Pesa wallet Journal Entry.")

	company = reference_doc.company or frappe.defaults.get_user_default("company")
	if not company:
		frappe.throw("Company is required to post the M-Pesa wallet Journal Entry.")

	debit_account, credit_account = get_mpesa_wallet_accounts(reference_doctype)

	branch_and_cost_center_dict = get_branch_and_cost_center_by_supplier(supplier=supplier)
	branch = branch_and_cost_center_dict.get("branch", "")
	cost_center = branch_and_cost_center_dict.get("cost_center", "")
	branch_cost_center_fields = {
		**({"branch": branch} if branch else {}),
		**({"cost_center": cost_center} if cost_center else {}),
	}

	driver_name = frappe.db.get_value("Driver", driver, "full_name") or driver
	if source_doctype == "Mpesa Express Request":
		cheque_no = payment_doc.transaction_id or payment_doc.name
	else:
		cheque_no = payment_doc.transid or payment_doc.name

	user_remark = (
		f"M-Pesa wallet recharge for driver {driver_name} - "
		f"{reference_doctype} {reference_doc.name} - {source_doctype} {payment_doc.name}"
	)

	journal_entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"posting_date": frappe.utils.nowdate(),
			"voucher_type": "Journal Entry",
			"company": company,
			"cheque_no": cheque_no,
			"cheque_date": frappe.utils.nowdate(),
			"user_remark": user_remark,
			"accounts": [
				{
					"account": debit_account,
					"debit_in_account_currency": amount,
					"credit_in_account_currency": 0,
					"party_type": "Supplier",
					"party": supplier,
					**branch_cost_center_fields,
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
		frappe.db.savepoint("mpesa_wallet_journal_entry")
		journal_entry.insert()
		journal_entry.submit()
		values = {"custom_songa_journal_entry": journal_entry.name}
		if source_doctype == "Mpesa Express Request":
			values["is_reconciled"] = 1
		frappe.db.set_value(
			source_doctype,
			payment_doc.name,
			values,
			update_modified=False,
		)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback(save_point="mpesa_wallet_journal_entry")
		raise

	return journal_entry.name


def _mpesa_songa_webhook_already_sent(
	payment_name, reference_doctype, source_doctype="Mpesa Express Request"
):
	action_type = _mpesa_wallet_action_type(reference_doctype)
	if not action_type:
		return False

	return bool(
		frappe.db.exists(
			"Songa Webhook Log",
			{
				"status": "Sent",
				"action_type": action_type,
				"reference_doctype": source_doctype,
				"reference_name": payment_name,
			},
		)
	)


def _mark_mpesa_wallet_processed(payment_name, source_doctype="Mpesa Express Request"):
	frappe.db.set_value(
		source_doctype,
		payment_name,
		{
			"custom_songa_wallet_processed": 1,
			"custom_songa_wallet_process_status": "Processed",
			"custom_songa_wallet_last_attempt_on": frappe.utils.now_datetime(),
		},
		update_modified=False,
	)


def record_mpesa_wallet_processing_failure(payment_name, source_doctype="Mpesa Express Request"):
	"""Increment failed attempt count and abandon when the max is reached."""
	attempt_count = (
		frappe.db.get_value(
			source_doctype,
			payment_name,
			"custom_songa_wallet_attempt_count",
		)
		or 0
	) + 1

	values = {
		"custom_songa_wallet_attempt_count": attempt_count,
		"custom_songa_wallet_last_attempt_on": frappe.utils.now_datetime(),
		"custom_songa_wallet_process_status": (
			"Abandoned" if attempt_count >= MAX_MPESA_WALLET_ATTEMPTS else "Pending"
		),
	}
	frappe.db.set_value(
		source_doctype,
		payment_name,
		values,
		update_modified=False,
	)
	frappe.db.commit()
	return values


@frappe.whitelist(allow_guest=False)
def reset_mpesa_wallet_processing(name):
	"""Reset an Abandoned wallet request so the cron (or a manual retry) can pick it up."""
	doc = frappe.get_doc("Mpesa Express Request", name)
	process_status = getattr(doc, "custom_songa_wallet_process_status", None) or "Pending"

	if process_status != "Abandoned":
		frappe.throw("Only Abandoned M-Pesa wallet requests can be reset for retry.")

	if getattr(doc, "custom_songa_wallet_processed", 0):
		frappe.throw("This M-Pesa request is already marked as wallet-processed.")

	frappe.db.set_value(
		"Mpesa Express Request",
		name,
		{
			"custom_songa_wallet_process_status": "Pending",
			"custom_songa_wallet_attempt_count": 0,
			"custom_songa_wallet_last_attempt_on": None,
			"custom_songa_wallet_processed": 0,
		},
		update_modified=False,
	)
	frappe.db.commit()
	return {
		"status": "success",
		"message": "M-Pesa wallet processing reset to Pending.",
		"name": name,
	}


@frappe.whitelist(allow_guest=False)
def retry_mpesa_wallet_processing(name):
	"""Reset Abandoned state if needed, then process the wallet request once."""
	doc = frappe.get_doc("Mpesa Express Request", name)
	process_status = getattr(doc, "custom_songa_wallet_process_status", None) or "Pending"

	if getattr(doc, "custom_songa_wallet_processed", 0) or process_status == "Processed":
		return {
			"status": "success",
			"message": "M-Pesa wallet processing already completed.",
			"name": name,
		}

	if process_status == "Abandoned":
		reset_mpesa_wallet_processing(name)
		doc.reload()

	try:
		process_mpesa_express_request(doc)
	except Exception as e:
		record_mpesa_wallet_processing_failure(name)
		return {
			"status": "error",
			"message": str(e),
			"name": name,
		}

	return {
		"status": "success",
		"message": "M-Pesa wallet processing completed.",
		"name": name,
	}


@frappe.whitelist(allow_guest=False)
def process_mpesa_express_request(doc):
	try:
		if getattr(doc, "custom_songa_wallet_processed", 0):
			return

		process_status = getattr(doc, "custom_songa_wallet_process_status", None) or "Pending"
		if process_status == "Abandoned":
			return

		attempt_count = getattr(doc, "custom_songa_wallet_attempt_count", 0) or 0
		if attempt_count >= MAX_MPESA_WALLET_ATTEMPTS:
			return

		if doc.status not in ("Completed", "Failed"):
			return

		if doc.reference_doctype not in ("Rental Days", "Energy KWh"):
			return

		reference_doctype = doc.reference_doctype
		reference_doc = frappe.get_doc(reference_doctype, doc.reference_name)

		if reference_doc.status != doc.status:
			try:
				frappe.db.savepoint("mpesa_express_request")
				frappe.db.set_value(reference_doctype, doc.reference_name, "status", doc.status)
				frappe.db.commit()
			except Exception:
				frappe.db.rollback(save_point="mpesa_express_request")
				raise

		if doc.status == "Completed":
			post_mpesa_wallet_journal_entry(doc, reference_doc)

			if not _mpesa_songa_webhook_already_sent(doc.name, reference_doctype):
				payload = {
					"driver_id": reference_doc.driver,
					"transaction_type": reference_doc.transaction_type,
					"amount": reference_doc.amount,
					"mpesa_express_request": doc.name,
					"action_type": _mpesa_wallet_action_type(reference_doctype),
				}

				if reference_doctype == "Rental Days":
					payload["rental_days_balance"] = get_rental_days_balance_by_driver(
						driver_id=reference_doc.driver
					)
				elif reference_doctype == "Energy KWh":
					payload["energy_kwh_balance"] = get_energy_kwh_balance_by_driver(
						driver_id=reference_doc.driver
					)

				send_songa_webhook(payload, context="Mpesa Express Request")
		else:
			frappe.logger().info(
				f"{reference_doctype} recharge cancelled for driver {reference_doc.driver} "
				f"due to failed M-Pesa payment."
			)

		_mark_mpesa_wallet_processed(doc.name)
		frappe.db.commit()

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Mpesa Express Request Workflow Error")
		frappe.throw(str(e))


def _clear_c2b_wallet_backref(c2b_name):
	frappe.db.set_value(
		"Mpesa C2B Payment Register",
		c2b_name,
		{
			"custom_songa_reference_doctype": None,
			"custom_songa_reference_name": None,
			"submit_payment": 0,
		},
		update_modified=False,
	)


def _cancel_linked_c2b_payment_entry(c2b_doc):
	payment_entry = getattr(c2b_doc, "payment_entry", None)
	if not payment_entry:
		return

	pe_docstatus = frappe.db.get_value("Payment Entry", payment_entry, "docstatus")
	if pe_docstatus != 1:
		return

	pe = frappe.get_doc("Payment Entry", payment_entry)
	pe.flags.ignore_links = True
	pe.cancel()


@frappe.whitelist(allow_guest=False)
def search_mpesa_c2b_for_wallet_link(full_name=None, transid=None, amount=None, limit=20):
	"""Search unlinked C2B payments eligible for Songa wallet linking."""
	if not any([full_name, transid, amount]):
		frappe.throw("Provide at least one of Full Name, Trans ID, or Amount.")

	try:
		limit = min(max(int(limit or 20), 1), 50)
	except (TypeError, ValueError):
		limit = 20

	filters = [
		["docstatus", "<", 2],
		["custom_songa_wallet_processed", "=", 0],
	]
	or_filters = [
		["custom_songa_reference_name", "is", "not set"],
		["custom_songa_reference_name", "=", ""],
	]

	if full_name:
		filters.append(["full_name", "like", f"%{full_name}%"])
	if transid:
		filters.append(["transid", "=", transid])
	if amount not in (None, ""):
		try:
			filters.append(["transamount", "=", float(amount)])
		except (TypeError, ValueError):
			frappe.throw("Amount must be a valid number.")

	rows = frappe.get_all(
		"Mpesa C2B Payment Register",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "transid", "full_name", "transamount", "transtime", "msisdn", "docstatus"],
		order_by="creation desc",
		limit_page_length=limit,
	)
	return {"status": "success", "data": rows}


@frappe.whitelist(allow_guest=False)
def link_mpesa_c2b_to_wallet(wallet_doctype, wallet_name, c2b_name):
	"""Link a C2B payment to a submitted In Progress wallet recharge."""
	if wallet_doctype not in ("Rental Days", "Energy KWh"):
		frappe.throw("C2B linking is only supported for Rental Days and Energy KWh.")

	wallet = frappe.get_doc(wallet_doctype, wallet_name)
	if wallet.docstatus != 1:
		frappe.throw("Wallet document must be submitted before linking a C2B payment.")
	if wallet.transaction_type != "Recharge":
		frappe.throw("Only Recharge documents can be linked to a C2B payment.")
	if wallet.status != "In Progress":
		frappe.throw("Wallet document must be In Progress to link a C2B payment.")
	if wallet.get("driver_commission_ledger") or wallet.get("mpesa_express_request"):
		frappe.throw("This recharge already has another payment channel linked.")
	if wallet.get("mpesa_c2b_payment_register"):
		frappe.throw("A C2B payment is already linked to this recharge.")

	c2b = frappe.get_doc("Mpesa C2B Payment Register", c2b_name)
	if c2b.docstatus == 2:
		frappe.throw("Cancelled C2B payments cannot be linked.")
	if getattr(c2b, "custom_songa_wallet_processed", 0):
		frappe.throw("This C2B payment is already marked as wallet-processed.")

	existing_ref = getattr(c2b, "custom_songa_reference_name", None)
	if existing_ref and existing_ref != wallet_name:
		frappe.throw(
			f"C2B payment {c2b_name} is already linked to "
			f"{c2b.custom_songa_reference_doctype} {existing_ref}."
		)

	wallet_amount = frappe.utils.flt(wallet.amount)
	c2b_amount = frappe.utils.flt(c2b.transamount)
	if wallet_amount != c2b_amount:
		frappe.throw(
			f"Amount mismatch: wallet amount is {wallet_amount} but C2B transamount is {c2b_amount}."
		)

	frappe.db.set_value(
		wallet_doctype,
		wallet_name,
		"mpesa_c2b_payment_register",
		c2b_name,
		update_modified=True,
	)
	frappe.db.set_value(
		"Mpesa C2B Payment Register",
		c2b_name,
		{
			"custom_songa_reference_doctype": wallet_doctype,
			"custom_songa_reference_name": wallet_name,
			"submit_payment": 0,
		},
		update_modified=False,
	)
	frappe.db.commit()

	return {
		"status": "success",
		"message": f"Linked C2B payment {c2b_name} to {wallet_doctype} {wallet_name}.",
		"c2b_name": c2b_name,
	}


@frappe.whitelist(allow_guest=False)
def unlink_mpesa_c2b_from_wallet(wallet_doctype, wallet_name):
	"""Unlink a C2B payment while the wallet recharge is still In Progress."""
	if wallet_doctype not in ("Rental Days", "Energy KWh"):
		frappe.throw("C2B unlinking is only supported for Rental Days and Energy KWh.")

	wallet = frappe.get_doc(wallet_doctype, wallet_name)
	c2b_name = wallet.get("mpesa_c2b_payment_register")
	if not c2b_name:
		frappe.throw("No C2B payment is linked to this document.")
	if wallet.status != "In Progress":
		frappe.throw("C2B can only be unlinked while the wallet recharge is In Progress.")

	if frappe.db.get_value("Mpesa C2B Payment Register", c2b_name, "custom_songa_wallet_processed"):
		frappe.throw("Cannot unlink a C2B payment that has already been wallet-processed.")

	frappe.db.set_value(wallet_doctype, wallet_name, "mpesa_c2b_payment_register", None)
	_clear_c2b_wallet_backref(c2b_name)
	frappe.db.commit()

	return {
		"status": "success",
		"message": f"Unlinked C2B payment {c2b_name} from {wallet_doctype} {wallet_name}.",
	}


@frappe.whitelist(allow_guest=False)
def process_mpesa_c2b_wallet_payment(wallet_doctype, wallet_name):
	"""Complete a C2B-linked wallet recharge: status Completed, JE, webhook."""
	if wallet_doctype not in ("Rental Days", "Energy KWh"):
		frappe.throw("C2B wallet completion is only supported for Rental Days and Energy KWh.")

	wallet = frappe.get_doc(wallet_doctype, wallet_name)
	c2b_name = wallet.get("mpesa_c2b_payment_register")
	if not c2b_name:
		frappe.throw("Link a Mpesa C2B Payment Register before completing this recharge.")
	if wallet.docstatus != 1:
		frappe.throw("Wallet document must be submitted.")
	if wallet.status not in ("In Progress", "Completed"):
		frappe.throw("Wallet document must be In Progress (or Completed for retry) to complete.")

	c2b = frappe.get_doc("Mpesa C2B Payment Register", c2b_name)

	if getattr(c2b, "custom_songa_wallet_processed", 0):
		if wallet.status != "Completed":
			frappe.db.set_value(wallet_doctype, wallet_name, "status", "Completed")
		return {
			"status": "success",
			"message": "C2B wallet processing already completed.",
			"wallet_name": wallet_name,
			"c2b_name": c2b_name,
		}

	if (
		c2b.get("custom_songa_reference_doctype") != wallet_doctype
		or c2b.get("custom_songa_reference_name") != wallet_name
	):
		frappe.throw("C2B payment is not linked to this wallet document.")

	wallet_amount = frappe.utils.flt(wallet.amount)
	c2b_amount = frappe.utils.flt(c2b.transamount)
	if wallet_amount != c2b_amount:
		frappe.throw(
			f"Amount mismatch: wallet amount is {wallet_amount} but C2B transamount is {c2b_amount}."
		)

	try:
		frappe.db.savepoint("mpesa_c2b_wallet_payment")
		_cancel_linked_c2b_payment_entry(c2b)

		post_mpesa_wallet_journal_entry(c2b, wallet)

		if wallet.status != "Completed":
			frappe.db.set_value(wallet_doctype, wallet_name, "status", "Completed")
			wallet.reload()

		if not _mpesa_songa_webhook_already_sent(
			c2b.name, wallet_doctype, source_doctype="Mpesa C2B Payment Register"
		):
			payload = {
				"driver_id": wallet.driver,
				"transaction_type": wallet.transaction_type,
				"amount": wallet.amount,
				"mpesa_c2b_payment_register": c2b.name,
				"action_type": _mpesa_wallet_action_type(wallet_doctype),
			}
			if wallet_doctype == "Rental Days":
				payload["rental_days_balance"] = get_rental_days_balance_by_driver(driver_id=wallet.driver)
			elif wallet_doctype == "Energy KWh":
				payload["energy_kwh_balance"] = get_energy_kwh_balance_by_driver(driver_id=wallet.driver)
			send_songa_webhook(payload, context="Mpesa C2B Payment Register")

		_mark_mpesa_wallet_processed(c2b.name, source_doctype="Mpesa C2B Payment Register")
		frappe.db.commit()
	except Exception as e:
		frappe.db.rollback(save_point="mpesa_c2b_wallet_payment")
		frappe.log_error(frappe.get_traceback(), "Mpesa C2B Wallet Processing Error")
		frappe.throw(str(e))

	return {
		"status": "success",
		"message": "C2B wallet recharge completed.",
		"wallet_name": wallet_name,
		"c2b_name": c2b_name,
	}


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
