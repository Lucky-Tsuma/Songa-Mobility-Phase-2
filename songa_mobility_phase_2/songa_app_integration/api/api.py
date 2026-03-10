import frappe
import json

@frappe.whitelist(allow_guest=False)
def allocate_commission():
    try:
        if not frappe.request.data:
            frappe.local.response["http_status_code"] = 400
            return {"status": "error", "message": "No data provided"}

        data = json.loads(frappe.request.data)

        if not data:
            frappe.local.response["http_status_code"] = 400
            return {"status": "error", "message": "No data provided"}

        driver_id = data.get("driver_id")
        company = data.get("company")
        amount = data.get("amount")

        missing = [f for f, v in {"driver_id": driver_id, "amount": amount}.items() if not v]
        if missing:
            frappe.local.response["http_status_code"] = 400
            return {"status": "error", "message": f"Missing required fields: {', '.join(missing)}"}

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