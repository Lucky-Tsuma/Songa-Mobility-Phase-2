import json

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
MAX_WEBHOOK_RETRY_ATTEMPTS = 5
WEBHOOK_RETRY_INTERVAL_MINUTES = 5


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


def _parse_payload(payload):
	if not payload:
		return {}
	if isinstance(payload, dict):
		return payload
	if isinstance(payload, str):
		try:
			return json.loads(payload)
		except json.JSONDecodeError:
			return {}
	return {}


def _get_webhook_url():
	return frappe.get_single("Songa Customization Settings").songa_webhook_endpoint


def _deliver_songa_webhook(url, payload):
	"""Post payload to Songa. Returns a result dict, never raises."""
	try:
		response = requests.post(url, json=payload, timeout=10, verify=True)
	except requests.exceptions.RequestException as e:
		return {
			"success": False,
			"http_status": None,
			"response_body": None,
			"error_message": f"Failed to reach Songa webhook: {e!s}",
		}

	if response.status_code != 200:
		return {
			"success": False,
			"http_status": response.status_code,
			"response_body": response.text,
			"error_message": (
				f"Songa webhook returned an error. "
				f"Status code: {response.status_code}, Response: {response.text}"
			),
		}

	return {
		"success": True,
		"http_status": response.status_code,
		"response_body": response.text,
		"error_message": None,
	}


def _find_existing_failed_log(payload):
	reference_doctype, reference_name = _extract_reference(payload)
	if not reference_doctype or not reference_name or not payload.get("action_type"):
		return None

	return frappe.db.get_value(
		"Songa Webhook Log",
		{
			"status": "Failed",
			"action_type": payload.get("action_type"),
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
		},
		"name",
	)


def log_failed_songa_webhook(
	*,
	context,
	payload=None,
	endpoint=None,
	http_status=None,
	error_message=None,
	response_body=None,
	webhook_log_name=None,
):
	"""Persist or update a failed Songa webhook attempt. Never raises to callers."""
	try:
		payload = _parse_payload(payload)
		reference_doctype, reference_name = _extract_reference(payload)
		driver = payload.get("driver_id")
		now = frappe.utils.now_datetime()

		if webhook_log_name:
			doc = frappe.get_doc("Songa Webhook Log", webhook_log_name)
		else:
			existing_name = _find_existing_failed_log(payload)
			if existing_name:
				doc = frappe.get_doc("Songa Webhook Log", existing_name)
			else:
				doc = frappe.get_doc(
					{
						"doctype": "Songa Webhook Log",
						"context": context or "Songa Webhook",
						"action_type": payload.get("action_type"),
						"reference_doctype": reference_doctype,
						"reference_name": reference_name,
						"driver": driver if driver and frappe.db.exists("Driver", driver) else None,
						"payload": frappe.as_json(payload, indent=2) if payload else None,
						"attempt_count": 0,
					}
				)

		doc.status = "Failed"
		doc.context = context or doc.context or "Songa Webhook"
		doc.action_type = payload.get("action_type") or doc.action_type
		doc.reference_doctype = reference_doctype or doc.reference_doctype
		doc.reference_name = reference_name or doc.reference_name
		if driver and frappe.db.exists("Driver", driver):
			doc.driver = driver
		doc.endpoint = endpoint or doc.endpoint
		doc.http_status = http_status
		doc.error_message = _truncate(error_message)
		doc.response_body = _truncate(response_body)
		doc.payload = frappe.as_json(payload, indent=2) if payload else doc.payload
		doc.attempt_count = (doc.attempt_count or 0) + 1
		doc.last_attempt_on = now
		doc.resolved_on = None

		if doc.is_new():
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)

		if doc.attempt_count >= MAX_WEBHOOK_RETRY_ATTEMPTS:
			doc.db_set(
				{
					"status": "Abandoned",
					"resolved_on": now,
				},
				update_modified=False,
			)

		return doc.name
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Songa Webhook Log")
		return None


def _mark_webhook_log_sent(doc, result):
	now = frappe.utils.now_datetime()
	doc.db_set(
		{
			"status": "Sent",
			"http_status": result.get("http_status"),
			"response_body": _truncate(result.get("response_body")),
			"error_message": None,
			"attempt_count": (doc.attempt_count or 0) + 1,
			"last_attempt_on": now,
			"resolved_on": now,
		},
		update_modified=True,
	)


def retry_songa_webhook_log(name, *, abandon_on_max_attempts=True):
	"""Retry a stored Songa webhook log. Returns a status dict, never raises."""
	doc = frappe.get_doc("Songa Webhook Log", name)

	if doc.status not in ("Failed", "Abandoned"):
		return {
			"status": "error",
			"message": f"Only Failed or Abandoned webhook logs can be retried. Current status: {doc.status}",
		}

	payload = _parse_payload(doc.payload)
	if not payload or not payload.get("action_type"):
		return {"status": "error", "message": "Webhook log is missing a valid payload with action_type."}

	url = doc.endpoint or _get_webhook_url()
	if not url:
		message = "Songa webhook endpoint not found, please check Songa Customization Settings."
		log_failed_songa_webhook(
			context=doc.context,
			payload=payload,
			error_message=message,
			webhook_log_name=doc.name,
		)
		return {"status": "error", "message": message}

	result = _deliver_songa_webhook(url, payload)
	if result["success"]:
		_mark_webhook_log_sent(doc, result)
		get_songa_webhook_logger().info(
			f"{doc.context}: Retry succeeded for {doc.name}. Payload: {payload}. "
			f"Response: {result.get('response_body')}"
		)
		return {"status": "success", "message": "Webhook sent successfully.", "name": doc.name}

	log_failed_songa_webhook(
		context=doc.context,
		payload=payload,
		endpoint=url,
		http_status=result.get("http_status"),
		error_message=result.get("error_message"),
		response_body=result.get("response_body"),
		webhook_log_name=doc.name,
	)

	message = result.get("error_message") or "Webhook delivery failed."
	if (
		abandon_on_max_attempts
		and frappe.db.get_value("Songa Webhook Log", doc.name, "status") == "Abandoned"
	):
		message = f"{message} Maximum retry attempts reached; log marked as Abandoned."

	return {"status": "error", "message": message, "name": doc.name}


@frappe.whitelist(allow_guest=False)
def retry_songa_webhook_log_from_desk(name):
	return retry_songa_webhook_log(name)


@frappe.whitelist(allow_guest=False)
def abandon_songa_webhook_log(name):
	doc = frappe.get_doc("Songa Webhook Log", name)
	if doc.status != "Failed":
		frappe.throw("Only Failed webhook logs can be abandoned.")

	doc.db_set(
		{
			"status": "Abandoned",
			"resolved_on": frappe.utils.now_datetime(),
		},
		update_modified=True,
	)
	return {"status": "success", "message": "Webhook log marked as Abandoned.", "name": doc.name}


def process_failed_songa_webhook_retries():
	"""Retry failed webhook logs that are due for another attempt."""
	cutoff = frappe.utils.add_to_date(None, minutes=-WEBHOOK_RETRY_INTERVAL_MINUTES)
	failed_logs = frappe.get_all(
		"Songa Webhook Log",
		filters={
			"status": "Failed",
			"attempt_count": ("<", MAX_WEBHOOK_RETRY_ATTEMPTS),
			"last_attempt_on": ("<=", cutoff),
		},
		pluck="name",
		order_by="last_attempt_on asc",
		limit=50,
	)

	for name in failed_logs:
		try:
			retry_songa_webhook_log(name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Songa Webhook Retry failed for {name}")


def send_songa_webhook(payload, *, context):
	"""
	Post a payload to the Songa webhook endpoint.

	Resolves the URL from Songa Customization Settings, posts JSON with a timeout,
	logs to songa_webhook_log, and records failures in Error Log and Songa Webhook Log.
	Returns True on success, False otherwise. Never raises for webhook delivery failures.
	"""
	payload = _parse_payload(payload)

	if not payload or not payload.get("action_type"):
		message = "Songa webhook payload must include action_type."
		frappe.log_error(title=context, message=message)
		log_failed_songa_webhook(context=context, payload=payload, error_message=message)
		return False

	url = _get_webhook_url()
	if not url:
		message = "Songa webhook endpoint not found, please check Songa Customization Settings."
		frappe.log_error(title=context, message=message)
		log_failed_songa_webhook(context=context, payload=payload, error_message=message)
		return False

	result = _deliver_songa_webhook(url, payload)
	if result["success"]:
		get_songa_webhook_logger().info(
			f"{context}: Sent to Songa. Payload: {payload}. Response: {result.get('response_body')}"
		)
		return True

	frappe.log_error(
		title=context,
		message=f"{result.get('error_message')}\nPayload: {payload}",
	)
	log_failed_songa_webhook(
		context=context,
		payload=payload,
		endpoint=url,
		http_status=result.get("http_status"),
		error_message=result.get("error_message"),
		response_body=result.get("response_body"),
	)
	return False
