import frappe
import json


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

        # TODO: Using a JE to allocate commission for simplicity, but we may want to consider other approaches depending on how Songa Mobility expects to receive this information and how it will be used in their system.
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
        journal_entry.insert()
        journal_entry.submit()

        frappe.set_value("Driver Commission Ledger", driver_commission_ledger_name, "journal_entry", journal_entry.name)
        frappe.db.commit()

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
def deduct_commission(wallet_request_name):
    try:
        wallet_request = frappe.get_doc("Wallet Request", wallet_request_name)
        driver = wallet_request.driver
        supplier = frappe.db.get_value("Driver", driver, "transporter")
        amount = wallet_request.amount

        if not frappe.db.exists("Driver", wallet_request.driver):
            frappe.throw("Driver not found")

        if not supplier:
            frappe.throw("Driver does not have an associated supplier")

        if amount <= 0:
            frappe.throw("Amount must be greater than zero for deduction")

        commission_balance = get_commission_balance(driver_id=driver)

        if commission_balance["status"] == "error":
            return commission_balance

        if commission_balance["balance"] < amount:
            frappe.throw(f"Insufficient commission balance. Available balance: {commission_balance['balance']}")

        expense_account, liability_account = get_expense_and_liability_accounts()

        journal_entry = frappe.get_doc(
            {
                "doctype": "Journal Entry",
                "posting_date": frappe.utils.nowdate(),
                "voucher_type": "Journal Entry",
                "company": wallet_request.company,
                "user_remark": f"Commission deduction for driver {wallet_request.driver_name} - Wallet Request {wallet_request.name}",
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
        journal_entry.insert()
        journal_entry.submit()

        frappe.set_value("Wallet Request", wallet_request_name, "journal_entry", journal_entry.name)

        # TODO: Find out how Songa Mobility handles driver trips and how it relates to commission deductions, implement accordingly. For now, we will create a Songa Trip linked to this wallet request to represent the deduction.
        songa_trip = frappe.get_doc({
            "doctype": "Songa Trip",
            "posting_date": frappe.utils.nowdate(),
            "wallet_request": wallet_request.name,
        })
        songa_trip.insert()
        songa_trip.submit()

        frappe.db.commit()

        return {
            "status": "success",
            "message": "Commission deducted successfully.",
            "data": {"journal_entry": journal_entry.name, "songa_trip": songa_trip.name},
        }
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Commission Deduction Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def get_commission_balance(driver_id=None):
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