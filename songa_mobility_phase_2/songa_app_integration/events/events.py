import re

import frappe
from frappe import _

from songa_mobility_phase_2.songa_app_integration.utils.songa_webhook import send_songa_webhook
from songa_mobility_phase_2.songa_app_integration.utils.utils import (
	get_commission_balance_by_driver,
)


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
			asset_repair_id = (
				frappe.db.get_value("Asset Repair", doc.reference_name, "custom_asset_repair_id")
				or doc.reference_name
			)

			payload = {
				"action_type": "asset_repair_comment",
				"asset_repair": doc.reference_name,
				"asset_repair_id": asset_repair_id,
				"comment": clean_content,
				"comment_owner": doc.owner,
				"comment_timestamp": doc.creation,
			}

			if not send_songa_webhook(payload, context="Asset Repair Comment"):
				return

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
		payload = {
			"action_type": ("Service Completed" if doc.repair_status == "Completed" else "Service Cancelled"),
			"asset_repair_id": doc.custom_asset_repair_id,
			"asset": doc.asset,
			"asset_name": doc.asset_name,
			"asset_type": doc.custom_asset_type,
			"severity_type": doc.custom_severity_type,
			"failure_date": str(doc.failure_date) if doc.failure_date else None,
			"completion_date": (str(doc.completion_date) if doc.completion_date else None),
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

		send_songa_webhook(payload, context="Asset Repair Completion")


def on_driver_insert(doc, method):
	if not doc.custom_supplier_group:
		frappe.log_error(
			f"Driver {doc.name} is missing Supplier Group. Cannot create linked Supplier/Customer.",
			"Driver Insert",
		)
		frappe.msgprint(
			_(f"Driver {doc.name} is missing Supplier Group. Cannot create linked Supplier/Customer."),
			alert=True,
		)
		return

	try:
		if not (doc.transporter and doc.customer):
			supplier = frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": doc.full_name,
					"supplier_type": "Individual",
					"supplier_group": doc.custom_supplier_group,
				}
			)
			supplier.save(ignore_permissions=True)

			customer = frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": doc.full_name,
					"customer_type": "Individual",
				}
			)
			customer.save(ignore_permissions=True)

			doc.transporter = supplier.name
			doc.customer = customer.name
			doc.save(ignore_permissions=True)

		party_link_exists = frappe.db.exists(
			"Party Link",
			{
				"primary_role": "Supplier",
				"primary_party": doc.transporter,
				"secondary_role": "Customer",
				"secondary_party": doc.customer,
			},
		) or frappe.db.exists(
			"Party Link",
			{
				"primary_role": "Customer",
				"primary_party": doc.customer,
				"secondary_role": "Supplier",
				"secondary_party": doc.transporter,
			},
		)
		if not party_link_exists:
			frappe.get_doc(
				{
					"doctype": "Party Link",
					"primary_role": "Supplier",
					"primary_party": doc.transporter,
					"secondary_role": "Customer",
					"secondary_party": doc.customer,
				}
			).save(ignore_permissions=True)

	except Exception:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Driver Insert Failed")
		frappe.throw("Failed to create linked Supplier/Customer. Please try again.")


def on_payment_entry_submit(doc, method):
	if not (doc.payment_type == "Pay" and doc.party_type == "Supplier" and doc.party):
		return

	driver_id = frappe.db.get_value("Driver", {"transporter": doc.party}, "name")
	if not driver_id:
		return

	commission_balance = get_commission_balance_by_driver(driver_id)
	if commission_balance["status"] == "error":
		frappe.log_error(
			title="Payment Entry Submission",
			message=f"Error fetching commission balance for driver {driver_id}: "
			f"{commission_balance['message']}",
		)
		return

	_send_commission_deduction_event(doc, driver_id, commission_balance)


def on_journal_entry_submit(doc, method):
	if not is_lease_payment_je(doc):
		return

	driver_id = _get_lease_payment_driver(doc)
	if not driver_id:
		return

	commission_balance = get_commission_balance_by_driver(driver_id)
	if commission_balance["status"] == "error":
		frappe.log_error(
			title="Journal Entry Submission",
			message=f"Error fetching commission balance for driver {driver_id}: "
			f"{commission_balance['message']}",
		)
		return

	_send_commission_deduction_event(doc, driver_id, commission_balance)


def on_purchase_invoice_validate(doc, method):
	for item in doc.items:
		item_branch = frappe.db.get_value("Item Default", {"parent": item.item_code}, "custom_branch")
		if item_branch and item.branch != item_branch:
			item.branch = item_branch

		item_cost_center = frappe.db.get_value(
			"Item Default", {"parent": item.item_code}, "buying_cost_center"
		)
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
	expense_account = settings.lease_to_own if asset_owner == "Customer" else settings.internal_consumption

	if not expense_account:
		return

	for item in doc.items:
		item.expense_account = expense_account


def _send_commission_deduction_event(doc, driver_id, commission_balance):
	payload = {
		"action_type": "Commission Deduction",
		"driver_id": driver_id,
		"commission_balance": commission_balance.get("balance"),
	}

	if doc.doctype == "Payment Entry":
		payload["payment_entry"] = doc.name
		payload["amount"] = doc.paid_amount
	elif doc.doctype == "Journal Entry":
		payload["journal_entry"] = doc.name
		payload["amount"] = doc.total_debit
	else:
		frappe.log_error(
			title="Commission Deduction Webhook",
			message=f"Unsupported doctype for commission deduction webhook: {doc.doctype}",
		)
		return

	send_songa_webhook(payload, context="Commission Deduction Webhook")


def _get_lease_payment_settings():
	settings = frappe.get_single("Songa Customization Settings")
	debit_account = settings.lease_payment_debit
	credit_account = settings.lease_payment_credit
	cost_center = settings.lease_payment_cost_center
	if not (debit_account and credit_account and cost_center):
		return None
	return {
		"debit_account": debit_account,
		"credit_account": credit_account,
		"cost_center": cost_center,
	}


def _get_lease_payment_debit_rows(doc, debit_account):
	if not getattr(doc, "accounts", None):
		return []

	return [
		row
		for row in doc.accounts
		if (
			row.account == debit_account
			and row.party_type == "Supplier"
			and row.party
			and (row.debit or 0) > 0
		)
	]


def _get_lease_payment_driver(doc, debit_account=None):
	"""Return the Active Driver linked to a lease-payment debit Supplier party."""
	if not debit_account:
		lease_settings = _get_lease_payment_settings()
		if not lease_settings:
			return None
		debit_account = lease_settings["debit_account"]

	for row in _get_lease_payment_debit_rows(doc, debit_account):
		driver_id = frappe.db.get_value("Driver", {"transporter": row.party, "status": "Active"}, "name")
		if driver_id:
			return driver_id
	return None


def is_lease_payment_je(doc):
	"""Return True if the Journal Entry is a lease payment against an active driver."""
	lease_settings = _get_lease_payment_settings()
	if not lease_settings:
		return False

	debit_rows = _get_lease_payment_debit_rows(doc, lease_settings["debit_account"])
	if not debit_rows:
		return False

	has_lease_credit = any(
		row.account == lease_settings["credit_account"]
		and row.cost_center == lease_settings["cost_center"]
		and (row.credit or 0) > 0
		for row in doc.accounts
	)
	if not has_lease_credit:
		return False

	return bool(_get_lease_payment_driver(doc, lease_settings["debit_account"]))
