import re

import frappe


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
		# TODO: Update song backend webhook here. Users can use comments or emails to communicate on the issue.
		clean_content = clean_comment(doc.content)
		print(f"New comment on {doc.reference_doctype} - {doc.reference_name}")
		print(f"By: {doc.owner}")
		print(f"Content: {clean_content}")
