import frappe
import requests

_songa_webhook_logger = None


def get_songa_webhook_logger():
	global _songa_webhook_logger
	if _songa_webhook_logger is None:
		frappe.utils.logger.set_log_level("INFO")
		_songa_webhook_logger = frappe.logger("songa_webhook_log", allow_site=True, file_count=20)
	return _songa_webhook_logger


def send_songa_webhook(payload, *, context):
	if not payload or not payload.get("action_type"):
		frappe.log_error(
			title=context,
			message="Songa webhook payload must include action_type.",
		)
		return False

	url = frappe.get_single("Songa Customization Settings").songa_webhook_endpoint
	if not url:
		frappe.log_error(
			title=context,
			message="Songa webhook endpoint not found, please check Songa Customization Settings.",
		)
		return False

	try:
		response = requests.post(url, json=payload, timeout=10, verify=True)
	except requests.exceptions.RequestException as e:
		frappe.log_error(
			title=context,
			message=f"Failed to reach Songa webhook: {e!s}\nPayload: {payload}",
		)
		return False

	if response.status_code != 200:
		frappe.log_error(
			title=context,
			message=(
				f"Songa webhook returned an error. "
				f"Status code: {response.status_code}, Response: {response.text}\n"
				f"Payload: {payload}"
			),
		)
		return False

	get_songa_webhook_logger().info(
		f"{context}: Sent to Songa. Payload: {payload}. Response: {response.text}"
	)
	return True
