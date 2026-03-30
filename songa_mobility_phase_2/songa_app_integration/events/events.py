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
	if (
		doc.comment_type == "Comment" and doc.reference_doctype == "Service Entry"
	):  # filter out system/likes/etc.
		try:
			clean_content = clean_comment(doc.content)
			url = frappe.get_single("Songa Customization Settings").songa_webhook_endpoint

			if not url:
				frappe.log_error(
					"Songa webhook endpoint not found, please check Songa Customization Settings",
					"Service Entry Comment",
				)
				return

			# initiate logger
			frappe.utils.logger.set_log_level("INFO")
			songa_webhook_logger = frappe.logger("songa_webhook_log", allow_site=True, file_count=20)

			payload = {
				"action_type": "service_entry_comment",
				"service_entry": doc.reference_name,
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
					"Service Entry Comment",
				)
				return

			songa_webhook_logger.info(
				f"New comment on {doc.reference_doctype} - {doc.reference_name} by {doc.owner}. Content: {clean_content}\n"
			)

		except Exception as e:
			frappe.log_error(
				f"Error processing comment for {doc.reference_doctype} - {doc.reference_name}: {e!s}",
				"Service Entry Comment",
			)
			raise
