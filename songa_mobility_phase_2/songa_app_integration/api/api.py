import frappe
import json
from frappe.model.workflow import apply_workflow
from ..utils.utils import get_commission_balance, deduct_commission

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

        driver_commission_ledger = frappe.get_doc({
            "doctype": "Driver Commission Ledger",
            "company": company or frappe.defaults.get_user_default("company"),
            "driver": driver,
            "amount": amount,
            "transaction_type": "Allocation"
        })
        driver_commission_ledger.insert()
        return {"status": "success", "message": "Commission allocation ledger created, please await approval.", "data": driver_commission_ledger}

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

        check_for_empty_values(data, ["driver_id", "amount", "no_of_days"])

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
        
        commission_balance = get_commission_balance(driver_id=driver_id)

        if commission_balance["status"] == "error":
            return commission_balance
        
        if amount > commission_balance["balance"]:
            frappe.local.response["http_status_code"] = 400
            return {"status": "error", "message": "Amount exceeds commission balance"}

        rental_days = frappe.get_doc({
            "doctype": "Rental Days",
            "company": company or frappe.defaults.get_user_default("company"),
            "posting_date": frappe.utils.nowdate(),
            "driver": driver,
            "no_of_days": no_of_days,
            "amount": amount,
            "status": "Available"
        })
        rental_days.insert()
        rental_days.submit()

        driver_commission_ledger = frappe.get_doc({
            "doctype": "Driver Commission Ledger",
            "company": company or frappe.defaults.get_user_default("company"),
            "driver": driver,
            "amount": amount,
            "usage": "Rental days recharge",
            "transaction_type": "Deduction"
        })

        driver_commission_ledger.insert()
        frappe.db.commit()

        deduct_commission(driver_commission_ledger.name, rental_days.name)
        apply_workflow(driver_commission_ledger, "Approve")
        return {"status": "success", "message": "Rental days recharged successfully.", "data": rental_days}
    

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

        check_for_empty_values(data, ["driver_id", "amount", "kwh"])

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

        commission_balance = get_commission_balance(driver_id=driver_id)

        if commission_balance["status"] == "error":
            return commission_balance
        
        if amount > commission_balance["balance"]:
            frappe.local.response["http_status_code"] = 400
            return {"status": "error", "message": "Amount exceeds commission balance"}

        energy_kwh = frappe.get_doc({
            "doctype": "Energy KWh",
            "company": company or frappe.defaults.get_user_default("company"),
            "posting_date": frappe.utils.nowdate(),
            "driver": driver,
            "energy_qty": kwh,
            "amount": amount,
            "status": "Available"
        })
        energy_kwh.insert()
        energy_kwh.submit()

        driver_commission_ledger = frappe.get_doc({
            "doctype": "Driver Commission Ledger",
            "company": company or frappe.defaults.get_user_default("company"),
            "driver": driver,
            "amount": amount,
            "usage": "Energy recharge",
            "transaction_type": "Deduction"
        })

        driver_commission_ledger.insert()
        frappe.db.commit()

        deduct_commission(driver_commission_ledger.name, None, energy_kwh.name)
        apply_workflow(driver_commission_ledger, "Approve")
        return {"status": "success", "message": "kWh recharged successfully.", "data": energy_kwh}

    except Exception as e:
        frappe.local.response["http_status_code"] = 500
        return {"status": "error", "message": str(e)}