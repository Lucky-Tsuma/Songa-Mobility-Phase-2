import json
import re

import frappe
import requests


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

			frappe.utils.logger.set_log_level("INFO")
			songa_webhook_logger = frappe.logger("songa_webhook_log", allow_site=True, file_count=20)

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

			songa_webhook_logger.info(
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
