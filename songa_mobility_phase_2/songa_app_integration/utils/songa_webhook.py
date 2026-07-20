import frappe
import requests

_songa_webhook_logger = None

_REFERENCE_KEYS = (
	("payment_entry", "Payment Entry"),
	("journal_entry", "Journal Entry"),
	("commission_ledger", "Driver Commission Ledger"),
	("asset_repair", "Asset Repair"),
	("mpesa_express_request", "Mpesa Express Request"),
)

_MAX_RESPONSE_LENGTH = 10000


def get_songa_webhook_logger():
	"""Return a shared Songa webhook logger."""
	global _songa_webhook_logger
	if _songa_webhook_logger is None:
		frappe.utils.logger.set_log_level("INFO")
		_songa_webhook_logger = frappe.logger("songa_webhook_log", allow_site=True, file_count=20)
	return _songa_webhook_logger


def _extract_reference(payload):
	if not payload:
		return None, None

	for key, doctype in _REFERENCE_KEYS:
		value = payload.get(key)
		if value:
			return doctype, value

	return None, None


def _truncate(value):
	if value is None:
		return None
	text = str(value)
	if len(text) <= _MAX_RESPONSE_LENGTH:
		return text
	return text[:_MAX_RESPONSE_LENGTH] + "\n...[truncated]"


def log_failed_songa_webhook(
	*,
	context,
	payload=None,
	endpoint=None,
	http_status=None,
	error_message=None,
	response_body=None,
):
	"""Persist a failed Songa webhook attempt. Never raises to callers."""
	try:
		payload = payload or {}
		reference_doctype, reference_name = _extract_reference(payload)
		driver = payload.get("driver_id")

		doc = frappe.get_doc(
			{
				"doctype": "Songa Webhook Log",
				"status": "Failed",
				"context": context or "Songa Webhook",
				"action_type": payload.get("action_type"),
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"driver": driver if driver and frappe.db.exists("Driver", driver) else None,
				"endpoint": endpoint,
				"http_status": http_status,
				"error_message": _truncate(error_message),
				"payload": frappe.as_json(payload, indent=2) if payload else None,
				"response_body": _truncate(response_body),
				"attempt_count": 1,
				"last_attempt_on": frappe.utils.now_datetime(),
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Songa Webhook Log")
		return None


def send_songa_webhook(payload, *, context):
	"""
	Post a payload to the Songa webhook endpoint.

	Resolves the URL from Songa Customization Settings, posts JSON with a timeout,
	logs to songa_webhook_log, and records failures in Error Log and Songa Webhook Log.
	Returns True on success, False otherwise. Never raises for webhook delivery failures.
	"""
	if not payload or not payload.get("action_type"):
		message = "Songa webhook payload must include action_type."
		frappe.log_error(title=context, message=message)
		log_failed_songa_webhook(
			context=context,
			payload=payload,
			error_message=message,
		)
		return False

	url = frappe.get_single("Songa Customization Settings").songa_webhook_endpoint
	if not url:
		message = "Songa webhook endpoint not found, please check Songa Customization Settings."
		frappe.log_error(title=context, message=message)
		log_failed_songa_webhook(
			context=context,
			payload=payload,
			error_message=message,
		)
		return False

	try:
		response = requests.post(url, json=payload, timeout=10, verify=True)
	except requests.exceptions.RequestException as e:
		message = f"Failed to reach Songa webhook: {e!s}"
		frappe.log_error(title=context, message=f"{message}\nPayload: {payload}")
		log_failed_songa_webhook(
			context=context,
			payload=payload,
			endpoint=url,
			error_message=message,
		)
		return False

	if response.status_code != 200:
		message = (
			f"Songa webhook returned an error. "
			f"Status code: {response.status_code}, Response: {response.text}"
		)
		frappe.log_error(title=context, message=f"{message}\nPayload: {payload}")
		log_failed_songa_webhook(
			context=context,
			payload=payload,
			endpoint=url,
			http_status=response.status_code,
			error_message=message,
			response_body=response.text,
		)
		return False

	get_songa_webhook_logger().info(
		f"{context}: Sent to Songa. Payload: {payload}. Response: {response.text}"
	)
	return True
