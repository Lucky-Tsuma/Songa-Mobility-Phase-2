import frappe
from songa_mobility_phase_2.songa_app_integration.utils.utils import get_commission_balance

TRIGGERED_STATES = {"Approved", "Rejected"}

def handle_commission_ledger_workflow(doc, method):
    if not doc.has_value_changed("workflow_state") or doc.workflow_state not in TRIGGERED_STATES:
        return

    try:
        return_payload = {
            "driver_id": doc.driver,
            "transaction_type": doc.transaction_type,
            "amount": doc.amount,
        }

        commission_balance = get_commission_balance(driver_id=doc.driver)
        return_payload["current_commission_balance"] = commission_balance.get("balance", 0)
            

        if doc.transaction_type == "Deduction":
            # return rental trip balance if deduction was used for rental trip
            # return KWh balance if deduction was used for EV charging
            # for now, we will just return the commission balance as we are only implementing commission deductions
            return_payload["deducted_amount"] = doc.amount

        # TODO: Get callback URL from Songa Mobility, add it to settings, and make a POST request to that URL with the payload
        print(f"\n\n\n\n\n Returned Payload: {return_payload} \n\n\n\n\n")
        return {"status": "success", "message": return_payload}
    except Exception as e:
        frappe.log_error(
            f"Error processing wallet request approval for {doc.name}: {str(e)}",
            "Wallet Request Workflow"
        )