# Copyright (c) 2026, Lucky Tsuma and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from songa_mobility_phase_2.songa_app_integration.utils.wallet_status import (
	on_wallet_cancel,
	validate_wallet_payment_links,
	validate_wallet_status,
)


class EnergyKWh(Document):
	def validate(self):
		validate_wallet_status(self)
		validate_wallet_payment_links(self)

	def on_cancel(self):
		on_wallet_cancel(self)
