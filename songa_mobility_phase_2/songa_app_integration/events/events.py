import json
import re

import frappe
import requests

from songa_mobility_phase_2.songa_app_integration.utils.utils import get_commission_balance_by_driver

_songa_webhook_logger = None


def get_songa_webhook_logger():
	"""Return a shared Songa webhook logger for this module."""
	global _songa_webhook_logger
	if _songa_webhook_logger is None:
		frappe.utils.logger.set_log_level("INFO")
		_songa_webhook_logger = frappe.logger("songa_webhook_log", allow_site=True, file_count=20)
	return _songa_webhook_logger


def clean_comment(html):
	# Replace block-level tags with newlines before stripping
	html = re.sub(r"<br\s*/?>", "\n", html)
	html = re.sub(r"</p>", "\n", html)
	html = re.sub(r"</div>", "\n", html)

	# Now strip remaining tags
	clean = frappe.utils.strip_html(html)

	# Clean up excess blank lines
	clean = re.sub(r"\n{3,}", "\n\n", clean).strip()

	return clean


def on_comment_update(doc, method):
	if doc.comment_type == "Comment" and doc.reference_doctype == "Asset Repair" and doc.published == 0:
		try:
			clean_content = clean_comment(doc.content)
			url = frappe.get_single("Songa Customization Settings").songa_webhook_endpoint

			if not url:
				frappe.log_error(
					"Songa webhook endpoint not found, please check Songa Customization Settings",
					"Asset Repair Comment",
				)
				return

			asset_repair_id = frappe.db.get_value(
				"Asset Repair", doc.reference_name, "custom_asset_repair_id"
			) or doc.reference_name

			payload = {
				"action_type": "asset_repair_comment",
				"asset_repair": doc.reference_name,
				"asset_repair_id": asset_repair_id,
				"comment": clean_content,
				"comment_owner": doc.owner,
				"comment_timestamp": doc.creation,
			}

			data = json.dumps(payload)
			headers = {"Content-Type": "application/json"}
			response = requests.post(url, data=data, headers=headers, verify=True)

			if response.status_code != 200:
				frappe.log_error(
					f"Failed to send comment to Songa webhook. Status code: {response.status_code}, Response: {response.text}",
					"Asset Repair Comment",
				)
				return

			get_songa_webhook_logger().info(
				f"New comment on {doc.reference_doctype} - {doc.reference_name} by {doc.owner}. Content: {clean_content}\n"
			)

			frappe.db.savepoint("comment_published_update")
			try:
				frappe.set_value("Comment", doc.name, "published", 1)
				frappe.db.commit()
			except Exception:
				frappe.db.rollback(save_point="comment_published_update")
				frappe.log_error(
					f"Rolled back published flag update for {doc.reference_doctype} - {doc.reference_name}",
					"Asset Repair Comment",
				)
				raise

		except Exception as e:
			frappe.log_error(
				f"Error processing comment for {doc.reference_doctype} - {doc.reference_name}: {e!s}",
				"Asset Repair Comment",
			)
			raise


def on_asset_repair_update(doc, method):
	if not doc.has_value_changed("workflow_state"):
		return

	if doc.workflow_state == "Completed" and doc.workflow_state != doc.get_doc_before_save().workflow_state:
		try:
			url = frappe.get_single("Songa Customization Settings").songa_webhook_endpoint

			if not url:
				frappe.log_error(
					"Songa webhook endpoint not found, please check Songa Customization Settings",
					"Asset Repair Completion",
				)
				return

			payload = {
				"action_type": "Service Completed" if doc.repair_status == "Completed" else "Service Cancelled",
				"asset_repair_id": doc.custom_asset_repair_id,
				"asset": doc.asset,
				"asset_name": doc.asset_name,
				"asset_type": doc.custom_asset_type,
				"severity_type": doc.custom_severity_type,
				"failure_date": str(doc.failure_date) if doc.failure_date else None,
				"completion_date": str(doc.completion_date) if doc.completion_date else None,
				"repair_status": doc.repair_status,
				"workflow_state": doc.workflow_state,
				"stock_consumption": doc.stock_consumption,
				"total_repair_cost": doc.total_repair_cost,
				"description": doc.description,
				"actions_performed": doc.actions_performed,
			}

			if doc.stock_consumption:
				payload["stock_items"] = [
					{
						"item_code": item.item_code,
						"warehouse": item.warehouse,
						"valuation_rate": item.valuation_rate,
						"uom": item.custom_uom,
						"consumed_quantity": item.consumed_quantity,
						"total_value": item.total_value,
					}
					for item in doc.stock_items
				]

			data = json.dumps(payload)
			headers = {"Content-Type": "application/json"}
			response = requests.post(url, data=data, headers=headers, verify=True)

			if response.status_code != 200:
				frappe.log_error(
					title="Asset Repair Completion",
					message=f"Failed to send asset repair completion to Songa webhook. Status code: {response.status_code}, Response: {response.text}\n Payload: {payload}",
				)
				return

			get_songa_webhook_logger().info(
				f"Asset Repair Completed - {doc.name} for Asset {doc.asset}. Sent completion event to Songa. Payload: {payload}"
			)

		except Exception as e:
			frappe.log_error(
				title="Asset Repair Completion",
				message=f"Error processing asset repair completion for {doc.name}: {e!s}\nPayload: {payload}",
			)
			raise

def on_driver_insert(doc, method):
    if not doc.custom_supplier_group:
        frappe.log_error(
            f"Driver {doc.name} is missing Supplier Group. Cannot create linked Supplier/Customer.",
            "Driver Insert",
        )
        frappe.msgprint(
            f"Driver {doc.name} is missing Supplier Group. Cannot create linked Supplier/Customer.",
            alert=True,
        )
        return

    try:
        if not (doc.transporter and doc.customer):
            supplier = frappe.get_doc({
                "doctype": "Supplier",
                "supplier_name": doc.full_name,
                "supplier_type": "Individual",
                "supplier_group": doc.custom_supplier_group,
            })
            supplier.save(ignore_permissions=True)

            customer = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": doc.full_name,
                "customer_type": "Individual",
            })
            customer.save(ignore_permissions=True)

            doc.transporter = supplier.name
            doc.customer = customer.name
            doc.save(ignore_permissions=True)

        party_link_exists = (
            frappe.db.exists("Party Link", {
                "primary_role": "Supplier",
                "primary_party": doc.transporter,
                "secondary_role": "Customer",
                "secondary_party": doc.customer,
            })
            or
            frappe.db.exists("Party Link", {
                "primary_role": "Customer",
                "primary_party": doc.customer,
                "secondary_role": "Supplier",
                "secondary_party": doc.transporter,
            })
        )
        if not party_link_exists:
            frappe.get_doc({
                "doctype": "Party Link",
                "primary_role": "Supplier",
                "primary_party": doc.transporter,
                "secondary_role": "Customer",
                "secondary_party": doc.customer,
            }).save(ignore_permissions=True)

    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Driver Insert Failed")
        frappe.throw("Failed to create linked Supplier/Customer. Please try again.")

def on_payment_entry_submit(doc, method):
	# TODO: Revisit this, optimize and refactor as needed. Send data to songa on submit, commented out currently.
	if doc.payment_type == "Pay" and doc.party_type == "Supplier":
		supplier_group = frappe.db.get_value("Supplier", doc.party, "supplier_group")
		if supplier_group:
			parent_supplier_group = frappe.db.get_value("Supplier Group", supplier_group, "parent_supplier_group")
			if parent_supplier_group == "Drivers / Collectors":
				driver_id = frappe.db.get_value("Driver", {"transporter": doc.party}, "name")
				if driver_id:
					commission_balance = get_commission_balance_by_driver(driver_id)
					if commission_balance["status"] == "error":
						frappe.throw(f"Error fetching commission balance: {commission_balance['message']}")
					else:
						try:
							url = frappe.get_single("Songa Customization Settings").songa_webhook_endpoint

							if not url:
								frappe.log_error(
									title="Payment Entry Submission",
									message=f"Songa webhook endpoint not found, please check Songa Customization Settings",
								)
								return

							payload = {
								"action_type": "Commission Deduction",
								"driver_id": driver_id,
								"payment_entry": doc.name,
								"amount": doc.paid_amount,
								"commission_balance": commission_balance.get("balance"),
							}
							data = json.dumps(payload)
							headers = {"Content-Type": "application/json"}
							response = requests.post(url, data=data, headers=headers, verify=True)

							if response.status_code != 200:
								frappe.log_error(
									title="Payment Entry Submission",
									message=f"Failed to send commission deduction to Songa webhook. Status code: {response.status_code}, Response: {response.text}",
								)
								return

							get_songa_webhook_logger().info(
								f"Payment Entry Submitted - {doc.name} for Driver {driver_id}. Sent commission deduction event to Songa."
							)
						except Exception as e:
							frappe.log_error(
								title="Payment Entry Submission",
								message=f"Error fetching Songa webhook endpoint: {e!s}",
							)
							return
			else:
				return
		else:
			return

def on_journal_entry_submit(doc, method):
    if not doc.is_system_generated or doc.voucher_type != "Journal Entry":
        return

    customer_credits = [
        entry for entry in doc.accounts
        if entry.party_type == "Customer" and entry.credit > 0
    ]

    supplier_debits = [
        entry for entry in doc.accounts
        if entry.party_type == "Supplier" and entry.debit > 0
    ]

    unique_customers = set(entry.party for entry in customer_credits)
    unique_suppliers = set(entry.party for entry in supplier_debits)

    if len(unique_customers) != 1 or len(unique_suppliers) != 1:
        return

    supplier = frappe.get_doc("Supplier", supplier_debits[0].party)

    driver_id = frappe.db.get_value("Driver", {"transporter": supplier.name}, "name")
    if not driver_id:
        return

    commission_balance = get_commission_balance_by_driver(driver_id)
    if commission_balance["status"] == "error":
        frappe.throw(f"Error fetching commission balance: {commission_balance['message']}")
    else:
        try:
            url = frappe.get_single("Songa Customization Settings").songa_webhook_endpoint
            if not url:
                frappe.log_error(
					title="Journal Entry Submission",
					message=f"Songa webhook endpoint not found, please check Songa Customization Settings",
				)
                return

            payload = {
                "action_type": "Commission Deduction",
                "driver_id": driver_id,
                "journal_entry": doc.name,
                "amount": doc.total_debit,
                "commission_balance": commission_balance.get("balance"),
            }
            data = json.dumps(payload)
            headers = {"Content-Type": "application/json"}

            response = requests.post(url, data=data, headers=headers, verify=True)
            if response.status_code != 200:
                frappe.log_error(
					title="Journal Entry Submission",
					message=f"Failed to send commission deduction to Songa webhook. Status code: {response.status_code}, Response: {response.text}",
                )
                return

            get_songa_webhook_logger().info(
                f"Journal Entry Submitted - {doc.name} for Driver {driver_id}. Sent commission deduction event to Songa."
            )
        except Exception as e:
            frappe.log_error(
				title="Journal Entry Submission",
				message=f"Error fetching Songa webhook endpoint: {e!s}",
			)
            return
		
def on_purchase_invoice_validate(doc, method):
	for item in doc.items:
			item_branch = frappe.db.get_value("Item Default", {"parent": item.item_code}, "custom_branch")
			if item_branch and item.branch != item_branch:
				item.branch = item_branch
				
			item_cost_center = frappe.db.get_value("Item Default", {"parent": item.item_code}, "buying_cost_center")
			if item_cost_center and item.cost_center != item_cost_center:
				item.cost_center = item_cost_center


def on_asset_repair_validate(doc, method):
	if not doc.asset:
		return

	asset_details = frappe.db.get_value(
		"Asset", doc.asset, ["cost_center", "branch", "custom_branch"], as_dict=True
	)
	if not asset_details:
		return

	if asset_details.cost_center:
		doc.cost_center = asset_details.cost_center

	branch = asset_details.custom_branch or asset_details.branch
	if branch:
		doc.branch = branch


def on_stock_entry_validate(doc, method):
	if doc.stock_entry_type != "Material Issue" or not doc.asset_repair:
		return

	asset = frappe.db.get_value("Asset Repair", doc.asset_repair, "asset")
	if not asset:
		return

	asset_owner = frappe.db.get_value("Asset", asset, "asset_owner")

	settings = frappe.get_single("Songa Customization Settings")
	expense_account = (
		settings.lease_to_own if asset_owner == "Customer" else settings.internal_consumption
	)

	if not expense_account:
		return

	for item in doc.items:
		item.expense_account = expense_account
