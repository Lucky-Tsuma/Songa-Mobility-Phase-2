# Copyright (c) 2026, Lucky Tsuma and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
    columns, data = get_columns(filters), get_data(filters)
    return columns, data


def get_data(filters=None):
    if not filters:
        filters = {}

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    driver = filters.get("driver")
    usage_filter = filters.get("usage") or "All"
    mode_of_payment = filters.get("mode_of_payment") or "All"

    if from_date and to_date and from_date > to_date:
        frappe.throw(_("From Date cannot be greater than To Date"))

    result = []

    # ── 1. Driver Commission Ledger entries ─────────────────────────────────
    #
    #   Shown when mode_of_payment is "All" or "Commission".
    #   When a usage filter is applied we restrict to Deductions that carry
    #   that usage; Allocations (which have no usage) are only returned when
    #   usage_filter == "All".
    # -------------------------------------------------------------------------
    if mode_of_payment in ("All", "Commission"):
        cl_filters = [["docstatus", "=", 1]]

        if from_date:
            cl_filters.append(["posting_date", ">=", from_date])
        if to_date:
            cl_filters.append(["posting_date", "<=", to_date])
        if driver:
            cl_filters.append(["driver", "=", driver])
        if usage_filter != "All":
            cl_filters.append(["usage", "=", usage_filter])

        commission_entries = frappe.get_all(
            "Driver Commission Ledger",
            filters=cl_filters,
            fields=[
                "name",
                "driver",
                "driver_name",
                "posting_date",
                "transaction_type",
                "usage",
                "amount",
                "journal_entry",
            ],
            order_by="posting_date asc, name asc",
        )

        for entry in commission_entries:
            result.append(
                {
                    "source": "Commission Ledger",
                    "commission_ledger": entry.name,
                    "driver": entry.driver,
                    "driver_name": entry.driver_name,
                    "posting_date": entry.posting_date,
                    "transaction_type": entry.transaction_type,
                    "usage": entry.usage,
                    "qty": None,
                    "amount": entry.amount,
                    "mode_of_payment": "Commission",
                    "journal_entry": entry.journal_entry,
                    "mpesa_transaction_id": None,
                }
            )

    # ── 2. Rental Days – Mpesa recharges ────────────────────────────────────
    #
    #   A Rental Days document counts here only when:
    #     • transaction_type == "Recharge"
    #     • mpesa_express_request is populated   (i.e. paid via Mpesa)
    #
    #   Shown when mode_of_payment is "All" / "Mpesa"  AND
    #             usage_filter     is "All" / "Rental days recharge".
    # -------------------------------------------------------------------------
    if mode_of_payment in ("All", "Mpesa") and usage_filter in (
        "All",
        "Rental days recharge",
    ):
        rd_filters = [
            ["docstatus", "=", 1],
            ["transaction_type", "=", "Recharge"],
            ["mpesa_express_request", "is", "set"],
        ]

        if from_date:
            rd_filters.append(["posting_date", ">=", from_date])
        if to_date:
            rd_filters.append(["posting_date", "<=", to_date])
        if driver:
            rd_filters.append(["driver", "=", driver])

        rental_entries = frappe.get_all(
            "Rental Days",
            filters=rd_filters,
            fields=[
                "name",
                "driver",
                "driver_name",
                "posting_date",
                "no_of_days",
                "amount",
                "mpesa_express_request",
            ],
            order_by="posting_date asc, name asc",
        )

        for entry in rental_entries:
            result.append(
                {
                    "source": "Rental Days",
                    "commission_ledger": None,
                    "driver": entry.driver,
                    "driver_name": entry.driver_name,
                    "posting_date": entry.posting_date,
                    "transaction_type": "Deduction",
                    "usage": "Rental days recharge",
                    "qty": entry.no_of_days,
                    "amount": entry.amount,
                    "mode_of_payment": "Mpesa",
                    "journal_entry": None,
                    "mpesa_transaction_id": entry.mpesa_express_request,
                }
            )

            frappe.msgprint(f"Rental Days entry {entry.name} for driver {entry.driver} has {entry.no_of_days} days")

    # ── 3. Energy KWh – Mpesa recharges ─────────────────────────────────────
    #
    #   Same logic as Rental Days but for Energy KWh documents.
    #   Shown when mode_of_payment is "All" / "Mpesa"  AND
    #             usage_filter     is "All" / "Energy recharge".
    # -------------------------------------------------------------------------
    if mode_of_payment in ("All", "Mpesa") and usage_filter in (
        "All",
        "Energy recharge",
    ):
        ek_filters = [
            ["docstatus", "=", 1],
            ["transaction_type", "=", "Recharge"],
            ["mpesa_express_request", "is", "set"],
        ]

        if from_date:
            ek_filters.append(["posting_date", ">=", from_date])
        if to_date:
            ek_filters.append(["posting_date", "<=", to_date])
        if driver:
            ek_filters.append(["driver", "=", driver])

        energy_entries = frappe.get_all(
            "Energy KWh",
            filters=ek_filters,
            fields=[
                "name",
                "driver",
                "driver_name",
                "posting_date",
                "energy_qty",
                "amount",
                "mpesa_express_request",
            ],
            order_by="posting_date asc, name asc",
        )

        for entry in energy_entries:
            result.append(
                {
                    "source": "Energy KWh",
                    "commission_ledger": None,
                    "driver": entry.driver,
                    "driver_name": entry.driver_name,
                    "posting_date": entry.posting_date,
                    "transaction_type": "Deduction",
                    "usage": "Energy recharge",
                    "qty": entry.energy_qty,
                    "amount": entry.amount,
                    "mode_of_payment": "Mpesa",
                    "journal_entry": None,
                    "mpesa_transaction_id": entry.mpesa_express_request,
                }
            )

            frappe.msgprint(f"Energy KWh entry {entry.name} for driver {entry.driver} has {entry.energy_qty} kWh")

    # Sort the merged result by driver first, then chronologically
    result.sort(key=lambda r: (r.get("driver") or "", str(r.get("posting_date") or "")))

    return result


def get_columns(filters=None):
    mode_of_payment = (filters or {}).get("mode_of_payment") or "All"

    columns = [
        {
            "label": _("Driver"),
            "fieldname": "driver",
            "fieldtype": "Link",
            "options": "Driver",
            "width": 120,
        },
        {
            "label": _("Driver Name"),
            "fieldname": "driver_name",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": _("Commission Ledger"),
            "fieldname": "commission_ledger",
            "fieldtype": "Link",
            "options": "Driver Commission Ledger",
            "width": 160,
        },
        {
            "label": _("Posting Date"),
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": _("Transaction Type"),
            "fieldname": "transaction_type",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "label": _("Usage"),
            "fieldname": "usage",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": _("Qty (Days / KWh)"),
            "fieldname": "qty",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("Amount"),
            "fieldname": "amount",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "label": _("Mode of Payment"),
            "fieldname": "mode_of_payment",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "label": _("Source"),
            "fieldname": "source",
            "fieldtype": "Data",
            "width": 150,
        },
    ]

    # Journal Entry column – only useful for Commission rows
    if mode_of_payment in ("All", "Commission"):
        columns.append(
            {
                "label": _("Journal Entry"),
                "fieldname": "journal_entry",
                "fieldtype": "Link",
                "options": "Journal Entry",
                "width": 150,
            }
        )

    # Mpesa Request column – only useful for Mpesa rows
    if mode_of_payment in ("All", "Mpesa"):
        columns.append(
            {
                "label": _("Mpesa Request"),
                "fieldname": "mpesa_transaction_id",
                "fieldtype": "Link",
                "options": "Mpesa Express Request",
                "width": 160,
            }
        )

    return columns
