# Copyright (c) 2026, Lucky Tsuma and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ServiceEntry(Document):
	def before_save(self):
		self.calculate_totals()

	def calculate_totals(self):
		total = 0
		for row in self.inventory_items:
			row.amount = (row.quantity or 0) * (row.rate or 0)
			total += row.amount
		self.total_amount = total
