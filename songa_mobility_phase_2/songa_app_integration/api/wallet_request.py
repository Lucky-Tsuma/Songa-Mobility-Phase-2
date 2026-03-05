import frappe
import json

@frappe.whitelist(allow_guest=False)
def make_wallet_request():
    try:
        if not frappe.request.data:
            frappe.local.response["http_status_code"] = 400
            return {"status": "error", "message": "No data provided"}

        data = json.loads(frappe.request.data)

        if not data:
            frappe.local.response["http_status_code"] = 400
            return {"status": "error", "message": "No data provided"}

        driver_id = data.get("driver_id")
        request_type = data.get("request_type")
        wallet_type = data.get("wallet_type")
        company = data.get("company")
        amount = data.get("amount")

        # Validating required fields
        missing = [f for f, v in {"driver_id": driver_id, "request_type": request_type, "wallet_type": wallet_type}.items() if not v]
        if missing:
            frappe.local.response["http_status_code"] = 400
            return {"status": "error", "message": f"Missing required fields: {', '.join(missing)}"}

        driver = frappe.db.get_value("Driver", driver_id, "name")
        if not driver:
            frappe.local.response["http_status_code"] = 404
            return {"status": "error", "message": "Driver not found"}

        wallet_types = frappe.get_list("Wallet Type", pluck="name")
        if not wallet_types:
            frappe.local.response["http_status_code"] = 400
            return {"status": "error", "message": "No wallet types defined in the system"}

        if wallet_type not in wallet_types:
            frappe.local.response["http_status_code"] = 400
            return {"status": "error", "message": "Wallet Type should be one of the following: " + ", ".join(wallet_types)}

        if wallet_type == "Driver rental trips" and request_type not in ["trip_commission", "mpesa"]:
            frappe.local.response["http_status_code"] = 400
            return {"status": "error", "message": "request_type must be either 'trip_commission' or 'mpesa'"}

        # Validate amount for all wallet types: must be present and a positive number
        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError
        except (TypeError, ValueError):
            frappe.local.response["http_status_code"] = 400
            return {"status": "error", "message": "A valid positive amount is required"}

        wallet_request = frappe.get_doc({
            "doctype": "Wallet Request",
            "company": company or frappe.defaults.get_user_default("company"),
            "driver": driver,
            "request_type": request_type,
            "wallet_type": wallet_type,
            "amount": amount,
        })
        wallet_request.insert()

        if wallet_type == "Driver commission":
            frappe.db.commit()
            frappe.local.response["http_status_code"] = 201
            return {"status": "success", "message": "Commission request created successfully, please wait for approval", "data": wallet_request.as_dict()}

        if request_type == "mpesa":
            # Do not insert yet — record will be created after mpesa confirmation
            frappe.db.rollback()
            frappe.local.response["http_status_code"] = 201
            return {"status": "success", "message": "Wallet request created successfully - mpesa"}
            # initiate_stk_push(wallet_request.name, amount)

        if request_type == "trip_commission":
            frappe.db.commit()
            frappe.local.response["http_status_code"] = 201
            return {"status": "success", "message": "Wallet request created successfully, please wait for approval", "data": wallet_request.as_dict()}

    except Exception as e:
        frappe.local.response["http_status_code"] = 500
        return {"status": "error", "message": str(e)}