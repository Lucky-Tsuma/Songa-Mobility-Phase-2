import frappe
from songa_mobility_phase_2.songa_app_integration.utils.utils import get_commission_balance

TRIGGERED_STATES = {"Approved", "Rejected"}
DRIVER_COMMISSION = "Driver commission"
DRIVER_RENTAL_TRIPS = "Driver rental trips"

def handle_wallet_request_workflow(doc, method):
    if not doc.has_value_changed("workflow_state") or doc.workflow_state not in TRIGGERED_STATES:
        return

    try:
        return _process_wallet_type(doc)
    except Exception as e:
        frappe.log_error(
            f"Error processing wallet request approval for {doc.name}: {str(e)}",
            "Wallet Request Workflow"
        )

def _process_wallet_type(doc):
    base_payload = {
        "driver": doc.driver,
        "wallet_request": doc.name,
        "workflow_state": doc.workflow_state,
    }

    if doc.wallet_type == DRIVER_COMMISSION:
        commission_balance = get_commission_balance(driver_id=doc.driver)
        base_payload["current_commission_balance"] = commission_balance.get("balance", 0)

    elif doc.wallet_type == DRIVER_RENTAL_TRIPS:
        result = frappe.db.get_all(
            "Songa Trip",
            filters={"driver": doc.driver},
            fields=["COUNT(name) as count"]
        )
        base_payload["total_rental_trips"] = result[0].get("count", 0) if result else 0

    else:
        return None

    # TODO: Get callback URL from Songa Mobility, add it to settings, and make a POST request to that URL with the payload
    print(f"\n\n\n\n\n Wallet Request Workflow Payload: {base_payload} \n\n\n\n\n")
    return {"status": "success", "message": base_payload}