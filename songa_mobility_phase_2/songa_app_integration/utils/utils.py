import json
import re

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

		if driver_commission_ledger.transaction_type != "Deduction":
			frappe.throw("Commission deduction is only supported for Deduction ledgers.")

		if driver_commission_ledger.journal_entry:
			return {
				"status": "success",
				"message": "Commission already deducted.",
				"data": driver_commission_ledger.journal_entry,
			}

		if driver_commission_ledger.workflow_state != "Approved":
			frappe.throw(
				"Driver Commission Ledger must be Approved before posting the deduction Journal Entry."
			)

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


def _mpesa_wallet_action_type(reference_doctype):
	if reference_doctype == "Rental Days":
		return "Rental days recharge"
	if reference_doctype == "Energy KWh":
		return "Energy recharge"
	return None


def _get_wallet_item_field(wallet_doctype):
	if wallet_doctype == "Rental Days":
		return "rental_recharge_item"
	if wallet_doctype == "Energy KWh":
		return "battery_swap_item"
	frappe.throw(f"Unsupported wallet doctype for M-Pesa Express billing: {wallet_doctype}")


def _get_stk_payment_settings():
	settings = frappe.get_single("Songa Customization Settings")
	required_fields = [
		"mpesa_express_mode_of_payment",
		"payment_gateway_account",
	]
	missing = [field for field in required_fields if not settings.get(field)]
	if missing:
		labels = [frappe.unscrub(field) for field in missing]
		frappe.throw("Please set the following fields on Songa Customization Settings: " + ", ".join(labels))
	return settings


def submit_sales_invoice(invoice):
	from frappe.model.workflow import apply_workflow

	return apply_workflow(invoice, "Submit")


def _wallet_si_remarks(wallet_doctype, wallet_name):
	return f"Songa Wallet|{wallet_doctype}|{wallet_name}"


def _create_sales_invoice_for_wallet_recharge(wallet_doc, *, item_code):
	driver = frappe.get_doc("Driver", wallet_doc.driver)
	if not driver.customer:
		frappe.throw("Driver does not have an associated customer.")

	item_uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": driver.customer,
			"company": wallet_doc.company,
			"posting_date": frappe.utils.nowdate(),
			"due_date": frappe.utils.nowdate(),
			"is_return": 0,
			"remarks": _wallet_si_remarks(wallet_doc.doctype, wallet_doc.name),
			"items": [
				{
					"item_code": item_code,
					"qty": 1,
					"uom": item_uom,
					"rate": wallet_doc.amount,
				}
			],
		}
	)
	invoice.insert(ignore_permissions=True)
	return submit_sales_invoice(invoice)


def _find_sales_invoice_for_wallet(wallet_doctype, wallet_name):
	"""Resolve the wallet Sales Invoice from C2B/PE links or remarks marker."""
	wallet = frappe.get_doc(wallet_doctype, wallet_name)
	c2b_name = wallet.get("mpesa_c2b_payment_register")
	if c2b_name:
		c2b = frappe.db.get_value(
			"Mpesa C2B Payment Register",
			c2b_name,
			["payment_entry", "billrefnumber"],
			as_dict=True,
		)
		if c2b:
			if c2b.payment_entry and frappe.db.exists("Payment Entry", c2b.payment_entry):
				refs = frappe.get_all(
					"Payment Entry Reference",
					filters={
						"parent": c2b.payment_entry,
						"reference_doctype": "Sales Invoice",
					},
					pluck="reference_name",
				)
				for ref in refs:
					if ref:
						return ref
			if c2b.billrefnumber and frappe.db.exists("Sales Invoice", c2b.billrefnumber):
				return c2b.billrefnumber

	marker = _wallet_si_remarks(wallet_doctype, wallet_name)
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"remarks": ["like", f"%{marker}%"],
			"docstatus": ["<", 2],
		},
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	return invoices[0] if invoices else None


def _parse_wallet_from_si_remarks(remarks):
	"""Return (wallet_doctype, wallet_name) from Sales Invoice remarks marker."""
	if not remarks:
		return None, None
	match = re.search(r"Songa Wallet\|(Rental Days|Energy KWh)\|([^\s|]+)", str(remarks))
	if not match:
		return None, None
	return match.group(1), match.group(2)


def _find_wallet_for_sales_invoice(sales_invoice_name):
	if not sales_invoice_name or not frappe.db.exists("Sales Invoice", sales_invoice_name):
		return None, None
	remarks = frappe.db.get_value("Sales Invoice", sales_invoice_name, "remarks")
	wallet_doctype, wallet_name = _parse_wallet_from_si_remarks(remarks)
	if not wallet_doctype or not wallet_name:
		return None, None
	if not frappe.db.exists(wallet_doctype, wallet_name):
		return None, None
	return wallet_doctype, wallet_name


def _resolve_sales_invoice_from_c2b(c2b):
	"""Resolve Sales Invoice from C2B BillRef or linked Payment Entry references."""
	billref = c2b.get("billrefnumber")
	if billref and frappe.db.exists("Sales Invoice", billref):
		return billref

	pe_name = c2b.get("payment_entry")
	if pe_name and frappe.db.exists("Payment Entry", pe_name):
		refs = frappe.get_all(
			"Payment Entry Reference",
			filters={
				"parent": pe_name,
				"reference_doctype": "Sales Invoice",
			},
			pluck="reference_name",
			order_by="idx asc",
		)
		for ref in refs:
			if ref and frappe.db.exists("Sales Invoice", ref):
				return ref
	return None


def complete_pending_wallet_for_c2b(c2b_name):
	"""
	When a C2B payment is submitted against a wallet Sales Invoice (BillRef = SI),
	link the C2B to the pending wallet and mark it Completed + webhook.

	Used after mpsa auto-reconciles PayBill payments that use the SI name as BillRef.
	"""
	if not c2b_name:
		return

	try:
		c2b = frappe.get_doc("Mpesa C2B Payment Register", c2b_name)
		if c2b.docstatus != 1:
			return

		linked_doctype, linked_name = _c2b_linked_wallet(c2b_name)
		if linked_doctype and linked_name:
			wallet = frappe.get_doc(linked_doctype, linked_name)
			if wallet.status == "Completed":
				return
			if wallet.status == "In Progress":
				process_mpesa_c2b_wallet_payment(linked_doctype, linked_name)
			return

		sales_invoice_name = _resolve_sales_invoice_from_c2b(c2b)
		if not sales_invoice_name:
			return

		wallet_doctype, wallet_name = _find_wallet_for_sales_invoice(sales_invoice_name)
		if not wallet_doctype:
			return

		wallet = frappe.get_doc(wallet_doctype, wallet_name)
		if wallet.docstatus != 1 or wallet.transaction_type != "Recharge":
			return
		if wallet.status == "Completed":
			return
		if wallet.status != "In Progress":
			return
		if wallet.get("driver_commission_ledger") or wallet.get("mpesa_express_request"):
			return
		existing_c2b = wallet.get("mpesa_c2b_payment_register")
		if existing_c2b and existing_c2b != c2b_name:
			return

		if not existing_c2b:
			_link_mpesa_c2b_to_wallet(wallet_doctype, wallet_name, c2b_name, commit=False)

		process_mpesa_c2b_wallet_payment(wallet_doctype, wallet_name)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Auto-complete C2B wallet for {c2b_name} failed",
		)


def create_wallet_c2b_sales_invoice(wallet_doctype, wallet_name):
	"""Create (or return existing) Sales Invoice for a C2B wallet recharge."""
	if wallet_doctype not in ("Rental Days", "Energy KWh"):
		frappe.throw("C2B wallet billing is only supported for Rental Days and Energy KWh.")

	existing = _find_sales_invoice_for_wallet(wallet_doctype, wallet_name)
	if existing:
		return frappe.get_doc("Sales Invoice", existing)

	wallet_doc = frappe.get_doc(wallet_doctype, wallet_name)
	if wallet_doc.docstatus != 1:
		frappe.throw("Wallet document must be submitted.")
	if wallet_doc.transaction_type != "Recharge":
		frappe.throw("Only Recharge documents can be billed through M-Pesa C2B.")

	settings = frappe.get_single("Songa Customization Settings")
	item_field = _get_wallet_item_field(wallet_doctype)
	item_code = settings.get(item_field)
	if not item_code:
		frappe.throw(
			"Please set the following field on Songa Customization Settings: " + frappe.unscrub(item_field)
		)

	return _create_sales_invoice_for_wallet_recharge(wallet_doc, item_code=item_code)


def _pe_allocates_to_sales_invoice(payment_entry_name, sales_invoice_name, amount=None):
	if not payment_entry_name or not frappe.db.exists("Payment Entry", payment_entry_name):
		return False
	pe = frappe.get_doc("Payment Entry", payment_entry_name)
	if pe.docstatus != 1:
		return False
	allocated = 0.0
	for ref in pe.references:
		if ref.reference_doctype == "Sales Invoice" and ref.reference_name == sales_invoice_name:
			allocated += frappe.utils.flt(ref.allocated_amount)
	if allocated <= 0:
		return False
	if amount is not None and abs(allocated - frappe.utils.flt(amount)) > 0.01:
		return False
	return True


def _allocate_existing_pe_to_sales_invoice(payment_entry_name, sales_invoice):
	"""Allocate an existing submitted PE against the Sales Invoice when possible."""
	from erpnext.accounts.party import get_party_account

	pe = frappe.get_doc("Payment Entry", payment_entry_name)
	if pe.docstatus != 1:
		frappe.throw(f"Payment Entry {payment_entry_name} is not submitted.")

	if _pe_allocates_to_sales_invoice(payment_entry_name, sales_invoice.name):
		return payment_entry_name

	unallocated = frappe.utils.flt(pe.unallocated_amount)
	if unallocated <= 0:
		frappe.throw(
			f"Payment Entry {payment_entry_name} has no unallocated amount to apply to "
			f"Sales Invoice {sales_invoice.name}."
		)

	sales_invoice.reload()
	reconcile_doc = frappe.new_doc("Payment Reconciliation")
	reconcile_doc.party_type = "Customer"
	reconcile_doc.party = sales_invoice.customer
	reconcile_doc.company = sales_invoice.company
	reconcile_doc.receivable_payable_account = get_party_account(
		"Customer", sales_invoice.customer, sales_invoice.company
	)

	invoice_data = {
		"invoice_type": "Sales Invoice",
		"invoice_number": sales_invoice.name,
		"invoice_date": sales_invoice.posting_date,
		"amount": sales_invoice.grand_total,
		"outstanding_amount": sales_invoice.outstanding_amount,
		"currency": sales_invoice.currency,
		"exchange_rate": 0,
	}
	payment_data = {
		"reference_type": "Payment Entry",
		"reference_name": pe.name,
		"posting_date": pe.posting_date,
		"amount": pe.unallocated_amount,
		"unallocated_amount": pe.unallocated_amount,
		"difference_amount": 0,
		"currency": pe.paid_from_account_currency or pe.paid_to_account_currency,
		"exchange_rate": 0,
	}
	args = {"invoices": [invoice_data], "payments": [payment_data]}
	reconcile_doc.append("invoices", invoice_data)
	reconcile_doc.append("payments", payment_data)
	reconcile_doc.allocate_entries(args)
	reconcile_doc.reconcile()

	sales_invoice.reload()
	if (
		not _pe_allocates_to_sales_invoice(payment_entry_name, sales_invoice.name)
		and frappe.utils.flt(sales_invoice.outstanding_amount) > 0.01
	):
		frappe.throw(
			f"Could not allocate Payment Entry {payment_entry_name} to Sales Invoice {sales_invoice.name}."
		)
	return payment_entry_name


def reconcile_c2b_to_sales_invoice(c2b_name, sales_invoice_name):
	"""Ensure C2B has a Payment Entry allocated to the wallet Sales Invoice. This is done via the Payment Entry workflow."""
	from frappe_mpsa_payments.frappe_mpsa_payments.api.payment_entry import create_payment_entry

	c2b = frappe.get_doc("Mpesa C2B Payment Register", c2b_name)
	sales_invoice = frappe.get_doc("Sales Invoice", sales_invoice_name)

	if sales_invoice.docstatus != 1:
		frappe.throw(f"Sales Invoice {sales_invoice_name} must be submitted.")

	amount = frappe.utils.flt(c2b.transamount)
	if (
		abs(amount - frappe.utils.flt(sales_invoice.grand_total)) > 0.01
		and frappe.utils.flt(sales_invoice.outstanding_amount) > 0.01
	):
		# Allow when SI outstanding matches payment (already partially paid elsewhere).
		if abs(amount - frappe.utils.flt(sales_invoice.outstanding_amount)) > 0.01:
			frappe.throw(
				f"Amount mismatch: C2B transamount is {amount} but Sales Invoice "
				f"outstanding is {sales_invoice.outstanding_amount}."
			)

	update_fields = {}
	if not c2b.customer:
		update_fields["customer"] = sales_invoice.customer
	elif c2b.customer != sales_invoice.customer:
		frappe.throw(
			f"C2B customer {c2b.customer} does not match Sales Invoice customer {sales_invoice.customer}."
		)
	if not c2b.company:
		update_fields["company"] = sales_invoice.company
	if c2b.billrefnumber != sales_invoice.name:
		update_fields["billrefnumber"] = sales_invoice.name
	if update_fields:
		frappe.db.set_value("Mpesa C2B Payment Register", c2b_name, update_fields, update_modified=False)
		c2b.reload()

	pe_name = c2b.payment_entry
	if pe_name and frappe.db.exists("Payment Entry", pe_name):
		pe_docstatus = frappe.db.get_value("Payment Entry", pe_name, "docstatus")
		if pe_docstatus == 1:
			if _pe_allocates_to_sales_invoice(pe_name, sales_invoice.name, amount):
				return pe_name
			# Prefer allocate-in-place when PE has unallocated amount.
			unallocated = frappe.utils.flt(
				frappe.db.get_value("Payment Entry", pe_name, "unallocated_amount")
			)
			if unallocated > 0:
				return _allocate_existing_pe_to_sales_invoice(pe_name, sales_invoice)
			# Wrong fully-allocated PE: cancel and recreate against this SI.
			_cancel_linked_c2b_payment_entry(c2b)
			frappe.db.set_value(
				"Mpesa C2B Payment Register", c2b_name, "payment_entry", None, update_modified=False
			)
			c2b.reload()
			pe_name = None
		elif pe_docstatus == 0:
			pe = frappe.get_doc("Payment Entry", pe_name)
			pe.set("references", [])
			pe.append(
				"references",
				{
					"reference_doctype": "Sales Invoice",
					"reference_name": sales_invoice.name,
					"allocated_amount": amount,
				},
			)
			pe.flags.ignore_permissions = True
			pe.save()
			pe.submit()
			return pe.name
		elif pe_docstatus == 2:
			frappe.db.set_value(
				"Mpesa C2B Payment Register", c2b_name, "payment_entry", None, update_modified=False
			)
			c2b.reload()
			pe_name = None

	if not pe_name:
		mode_of_payment = c2b.mode_of_payment
		if not mode_of_payment:
			mode_of_payment = frappe.db.get_single_value(
				"Songa Customization Settings", "mpesa_c2b_mode_of_payment"
			)
			if mode_of_payment:
				frappe.db.set_value(
					"Mpesa C2B Payment Register",
					c2b_name,
					"mode_of_payment",
					mode_of_payment,
					update_modified=False,
				)
				c2b.mode_of_payment = mode_of_payment

		if not mode_of_payment:
			frappe.throw(
				f"Mode of Payment is required for Mpesa C2B Payment Register {c2b_name}. "
				"Set it on the C2B record or on Songa Customization Settings "
				"(Mpesa C2B Mode of Payment)."
			)
		if not c2b.company:
			frappe.throw(f"Company is required on Mpesa C2B Payment Register {c2b_name}.")
		if not c2b.customer:
			frappe.throw(f"Customer is required on Mpesa C2B Payment Register {c2b_name}.")

		# Prefer stock C2B submit path when register is still draft.
		if c2b.docstatus == 0:
			c2b.submit_payment = 1
			c2b.flags.ignore_permissions = True
			c2b.save()
			c2b.submit()
			c2b.reload()
			if c2b.payment_entry:
				return c2b.payment_entry

		payment_entry = create_payment_entry(
			c2b.company,
			c2b.customer,
			amount,
			c2b.currency or sales_invoice.currency,
			mode_of_payment,
			"Customer",
			c2b.posting_date,
			c2b.name,
			c2b.posting_date,
			None,
			1,
			references=[
				{
					"reference_doctype": "Sales Invoice",
					"reference_name": sales_invoice.name,
					"allocated_amount": amount,
				}
			],
		)
		frappe.db.set_value(
			"Mpesa C2B Payment Register",
			c2b_name,
			"payment_entry",
			payment_entry.name,
			update_modified=False,
		)
		return payment_entry.name

	return pe_name


def _create_payment_request_for_wallet_recharge(*, sales_invoice, phone_number, settings):
	gateway_account = frappe.get_doc("Payment Gateway Account", settings.payment_gateway_account)
	if not gateway_account.payment_gateway:
		frappe.throw("Payment Gateway is required on the selected Payment Gateway Account.")
	if not gateway_account.payment_account:
		frappe.throw("Payment Account is required on the selected Payment Gateway Account.")
	if gateway_account.payment_channel and gateway_account.payment_channel != "Phone":
		frappe.throw("Selected Payment Gateway Account must use Phone payment channel.")

	payment_request = frappe.get_doc(
		{
			"doctype": "Payment Request",
			"payment_request_type": "Inward",
			"reference_doctype": "Sales Invoice",
			"reference_name": sales_invoice.name,
			"party_type": "Customer",
			"party": sales_invoice.customer,
			"party_name": sales_invoice.customer_name,
			"company": sales_invoice.company,
			"currency": sales_invoice.currency,
			"grand_total": sales_invoice.outstanding_amount or sales_invoice.grand_total,
			"outstanding_amount": sales_invoice.outstanding_amount or sales_invoice.grand_total,
			"mode_of_payment": settings.mpesa_express_mode_of_payment,
			"payment_gateway_account": settings.payment_gateway_account,
			"payment_gateway": gateway_account.payment_gateway,
			"payment_account": gateway_account.payment_account,
			"payment_channel": gateway_account.payment_channel or "Phone",
			"phone_number": phone_number,
			"email_to": frappe.session.user,
			"subject": f"Wallet recharge payment request for {sales_invoice.name}",
			"mute_email": 1,
		}
	)
	payment_request.insert(ignore_permissions=True)
	payment_request.submit()
	return payment_request


def _find_mpesa_express_request_for_payment_request(payment_request_name):
	requests = frappe.get_all(
		"Mpesa Express Request",
		filters={
			"reference_doctype": "Payment Request",
			"reference_name": payment_request_name,
		},
		fields=["name"],
		order_by="creation desc",
		limit=1,
	)
	if not requests:
		frappe.throw(f"No Mpesa Express Request was created for Payment Request {payment_request_name}.")
	return requests[0].name


def create_wallet_mpesa_express_request(wallet_doctype, wallet_name, *, phone_number):
	"""Create SI+PR and return the resulting Mpesa Express Request for a wallet recharge."""
	if wallet_doctype not in ("Rental Days", "Energy KWh"):
		frappe.throw("M-Pesa Express wallet billing is only supported for Rental Days and Energy KWh.")

	wallet_doc = frappe.get_doc(wallet_doctype, wallet_name)
	if wallet_doc.docstatus != 1:
		frappe.throw("Wallet document must be submitted.")
	if wallet_doc.transaction_type != "Recharge":
		frappe.throw("Only Recharge documents can be billed through M-Pesa Express.")

	settings = _get_stk_payment_settings()
	item_field = _get_wallet_item_field(wallet_doctype)
	item_code = settings.get(item_field)
	if not item_code:
		frappe.throw(
			"Please set the following field on Songa Customization Settings: " + frappe.unscrub(item_field)
		)

	sales_invoice = _create_sales_invoice_for_wallet_recharge(wallet_doc, item_code=item_code)
	payment_request = _create_payment_request_for_wallet_recharge(
		sales_invoice=sales_invoice,
		phone_number=phone_number,
		settings=settings,
	)
	mpesa_express_request = _find_mpesa_express_request_for_payment_request(payment_request.name)
	return {
		"sales_invoice": sales_invoice.name,
		"payment_request": payment_request.name,
		"mpesa_express_request": mpesa_express_request,
	}


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


@frappe.whitelist(allow_guest=False)
def retry_mpesa_wallet_processing(name):
	"""Re-run wallet status sync / webhook for a terminal Express request."""
	doc = frappe.get_doc("Mpesa Express Request", name)
	if doc.status not in ("Completed", "Failed"):
		return {
			"status": "error",
			"message": "M-Pesa Express Request must be Completed or Failed.",
			"name": name,
		}

	try:
		process_mpesa_express_request(doc)
	except Exception as e:
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
		if doc.status not in ("Completed", "Failed"):
			return

		wallet = frappe.db.get_value(
			"Rental Days",
			{"mpesa_express_request": doc.name},
			["name", "driver", "amount", "transaction_type", "no_of_days", "status"],
			as_dict=True,
		)
		wallet_doctype = "Rental Days"

		if not wallet:
			wallet = frappe.db.get_value(
				"Energy KWh",
				{"mpesa_express_request": doc.name},
				["name", "driver", "amount", "transaction_type", "energy_qty", "status"],
				as_dict=True,
			)
			wallet_doctype = "Energy KWh"

		if not wallet:
			return

		if wallet.status != doc.status:
			try:
				frappe.db.savepoint("mpesa_express_request")
				frappe.db.set_value(wallet_doctype, wallet.name, "status", doc.status)
				frappe.db.commit()
			except Exception:
				frappe.db.rollback(save_point="mpesa_express_request")
				raise

		if doc.status == "Completed":
			if not _mpesa_songa_webhook_already_sent(doc.name, wallet_doctype):
				payload = {
					"driver_id": wallet.driver,
					"transaction_type": wallet.transaction_type,
					"amount": wallet.amount,
					"mpesa_express_request": doc.name,
					"action_type": _mpesa_wallet_action_type(wallet_doctype),
				}

				if wallet_doctype == "Rental Days":
					rental_balance = get_rental_days_balance_by_driver(driver_id=wallet.driver)
					if rental_balance.get("status") == "success":
						payload["rental_days_balance"] = rental_balance.get("total_rental_days", 0)
					payload["rental_day_id"] = wallet.name
					payload["no_of_days"] = wallet.no_of_days
				elif wallet_doctype == "Energy KWh":
					energy_balance = get_energy_kwh_balance_by_driver(driver_id=wallet.driver)
					if energy_balance.get("status") == "success":
						payload["energy_kwh_balance"] = energy_balance.get("total_kwh", 0)
					payload["energy_kwh_id"] = wallet.name
					payload["kwh"] = wallet.energy_qty

				send_songa_webhook(payload, context="Mpesa Express Request")
		else:
			frappe.logger().info(
				f"{wallet_doctype} recharge cancelled for driver {wallet.driver} "
				f"due to failed M-Pesa payment."
			)

		frappe.db.commit()

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Mpesa Express Request Workflow Error")
		frappe.throw(str(e))


def _c2b_linked_wallet(c2b_name):
	"""Return (wallet_doctype, wallet_name) if a wallet links this C2B register."""
	for wallet_doctype in ("Rental Days", "Energy KWh"):
		wallet_name = frappe.db.get_value(
			wallet_doctype,
			{"mpesa_c2b_payment_register": c2b_name},
			"name",
		)
		if wallet_name:
			return wallet_doctype, wallet_name
	return None, None


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


def find_eligible_c2b_by_transid(transid, amount):
	"""
	Find an unlinked C2B payment by exact transid.

	Locks matching rows FOR UPDATE. Returns a result dict:
	- success: {"status": "success", "c2b_name": ...}
	- error: {"status": "error", "http_status_code": ..., "message": ...}
	"""
	if not transid:
		return {
			"status": "error",
			"http_status_code": 400,
			"message": "transaction_id is required",
		}

	rows = frappe.db.sql(
		"""
		SELECT
			c2b.name,
			c2b.transamount
		FROM `tabMpesa C2B Payment Register` c2b
		WHERE c2b.transid = %s
		  AND c2b.docstatus < 2
		  AND NOT EXISTS (
			SELECT 1 FROM `tabRental Days` rd
			WHERE rd.mpesa_c2b_payment_register = c2b.name
		  )
		  AND NOT EXISTS (
			SELECT 1 FROM `tabEnergy KWh` ek
			WHERE ek.mpesa_c2b_payment_register = c2b.name
		  )
		ORDER BY c2b.creation DESC
		FOR UPDATE
		""",
		(transid,),
		as_dict=True,
	)

	if not rows:
		# Distinguish not found vs already linked
		any_rows = frappe.db.sql(
			"""
			SELECT name, transamount
			FROM `tabMpesa C2B Payment Register`
			WHERE transid = %s AND docstatus < 2
			ORDER BY creation DESC
			LIMIT 1
			""",
			(transid,),
			as_dict=True,
		)
		if not any_rows:
			return {
				"status": "error",
				"http_status_code": 404,
				"message": f"No M-Pesa C2B payment found for transaction_id {transid}",
			}
		return {
			"status": "error",
			"http_status_code": 400,
			"message": (f"M-Pesa C2B payment for transaction_id {transid} is already linked to a wallet."),
		}

	expected_amount = frappe.utils.flt(amount)
	amount_matches = [row for row in rows if frappe.utils.flt(row.transamount) == expected_amount]
	if not amount_matches:
		found_amount = frappe.utils.flt(rows[0].transamount)
		return {
			"status": "error",
			"http_status_code": 400,
			"message": (
				f"Amount mismatch: wallet amount is {expected_amount} but "
				f"C2B transamount is {found_amount} for transaction_id {transid}."
			),
		}

	return {"status": "success", "c2b_name": amount_matches[0].name}


@frappe.whitelist(allow_guest=False)
def search_mpesa_c2b_for_wallet_link(full_name=None, transid=None, amount=None, limit=20):
	"""Search unlinked C2B payments eligible for Songa wallet linking."""
	if not any([full_name, transid, amount]):
		frappe.throw("Provide at least one of Full Name, Trans ID, or Amount.")

	try:
		limit = min(max(int(limit or 20), 1), 50)
	except (TypeError, ValueError):
		limit = 20

	conditions = ["c2b.docstatus < 2"]
	values = []
	if full_name:
		conditions.append("c2b.full_name LIKE %s")
		values.append(f"%{full_name}%")
	if transid:
		conditions.append("c2b.transid = %s")
		values.append(transid)
	if amount not in (None, ""):
		try:
			conditions.append("c2b.transamount = %s")
			values.append(float(amount))
		except (TypeError, ValueError):
			frappe.throw("Amount must be a valid number.")

	values.append(limit)
	rows = frappe.db.sql(
		f"""
		SELECT
			c2b.name,
			c2b.transid,
			c2b.full_name,
			c2b.transamount,
			c2b.transtime,
			c2b.msisdn,
			c2b.docstatus
		FROM `tabMpesa C2B Payment Register` c2b
		WHERE {" AND ".join(conditions)}
		  AND NOT EXISTS (
			SELECT 1 FROM `tabRental Days` rd
			WHERE rd.mpesa_c2b_payment_register = c2b.name
		  )
		  AND NOT EXISTS (
			SELECT 1 FROM `tabEnergy KWh` ek
			WHERE ek.mpesa_c2b_payment_register = c2b.name
		  )
		ORDER BY c2b.creation DESC
		LIMIT %s
		""",
		tuple(values),
		as_dict=True,
	)
	return {"status": "success", "data": rows}


def _link_mpesa_c2b_to_wallet(wallet_doctype, wallet_name, c2b_name, *, commit=True):
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

	linked_doctype, linked_name = _c2b_linked_wallet(c2b_name)
	if linked_name and linked_name != wallet_name:
		frappe.throw(f"C2B payment {c2b_name} is already linked to {linked_doctype} {linked_name}.")

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

	c2b_update = {}
	sales_invoice_name = _find_sales_invoice_for_wallet(wallet_doctype, wallet_name)
	if sales_invoice_name:
		c2b_update["billrefnumber"] = sales_invoice_name
		si_customer = frappe.db.get_value("Sales Invoice", sales_invoice_name, "customer")
		if si_customer and not c2b.customer:
			c2b_update["customer"] = si_customer

	if c2b_update:
		frappe.db.set_value(
			"Mpesa C2B Payment Register",
			c2b_name,
			c2b_update,
			update_modified=False,
		)
	if commit:
		frappe.db.commit()

	return {
		"status": "success",
		"message": f"Linked C2B payment {c2b_name} to {wallet_doctype} {wallet_name}.",
		"c2b_name": c2b_name,
		"sales_invoice": sales_invoice_name,
	}


@frappe.whitelist(allow_guest=False)
def link_mpesa_c2b_to_wallet(wallet_doctype, wallet_name, c2b_name):
	"""Link a C2B payment to a submitted In Progress wallet recharge."""
	return _link_mpesa_c2b_to_wallet(wallet_doctype, wallet_name, c2b_name, commit=True)


def link_and_complete_mpesa_c2b_recharge(wallet_doctype, wallet_name, c2b_name):
	"""Link a C2B payment and complete the wallet via SI Payment Entry + webhook."""
	_link_mpesa_c2b_to_wallet(wallet_doctype, wallet_name, c2b_name, commit=False)
	return process_mpesa_c2b_wallet_payment(wallet_doctype, wallet_name)


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

	frappe.db.set_value(wallet_doctype, wallet_name, "mpesa_c2b_payment_register", None)
	frappe.db.commit()

	return {
		"status": "success",
		"message": f"Unlinked C2B payment {c2b_name} from {wallet_doctype} {wallet_name}.",
	}


@frappe.whitelist(allow_guest=False)
def process_mpesa_c2b_wallet_payment(wallet_doctype, wallet_name):
	"""Complete a C2B-linked wallet recharge: PE against SI, status Completed, webhook."""
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

	if wallet.status == "Completed":
		return {
			"status": "success",
			"message": "C2B wallet processing already completed.",
			"wallet_name": wallet_name,
			"c2b_name": c2b_name,
			"sales_invoice": _find_sales_invoice_for_wallet(wallet_doctype, wallet_name),
		}

	wallet_amount = frappe.utils.flt(wallet.amount)
	c2b_amount = frappe.utils.flt(c2b.transamount)
	if wallet_amount != c2b_amount:
		frappe.throw(
			f"Amount mismatch: wallet amount is {wallet_amount} but C2B transamount is {c2b_amount}."
		)

	try:
		frappe.db.savepoint("mpesa_c2b_wallet_payment")

		sales_invoice = create_wallet_c2b_sales_invoice(wallet_doctype, wallet_name)
		payment_entry_name = reconcile_c2b_to_sales_invoice(c2b_name, sales_invoice.name)

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
				"sales_invoice": sales_invoice.name,
				"payment_entry": payment_entry_name,
				"action_type": _mpesa_wallet_action_type(wallet_doctype),
			}
			if wallet_doctype == "Rental Days":
				rental_balance = get_rental_days_balance_by_driver(driver_id=wallet.driver)
				if rental_balance.get("status") == "success":
					payload["rental_days_balance"] = rental_balance.get("total_rental_days", 0)
				payload["rental_day_id"] = wallet.name
				payload["no_of_days"] = wallet.no_of_days
			elif wallet_doctype == "Energy KWh":
				energy_balance = get_energy_kwh_balance_by_driver(driver_id=wallet.driver)
				if energy_balance.get("status") == "success":
					payload["energy_kwh_balance"] = energy_balance.get("total_kwh", 0)
				payload["energy_kwh_id"] = wallet.name
				payload["kwh"] = wallet.energy_qty
			send_songa_webhook(payload, context="Mpesa C2B Payment Register")

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
		"sales_invoice": sales_invoice.name,
		"payment_entry": payment_entry_name,
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
