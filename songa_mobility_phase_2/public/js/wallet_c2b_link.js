frappe.provide("frappe.songa_wallet_c2b");

frappe.songa_wallet_c2b.UTILS = "songa_mobility_phase_2.songa_app_integration.utils.utils";

frappe.songa_wallet_c2b.call = (method, args, frm, successMessage) => {
	frappe.call({
		method: `${frappe.songa_wallet_c2b.UTILS}.${method}`,
		args,
		freeze: true,
		freeze_message: __("Processing..."),
		callback(r) {
			if (r.message?.status === "success") {
				frappe.show_alert({ message: successMessage, indicator: "green" });
				frm.reload_doc();
				return;
			}

			frappe.msgprint({
				title: __("C2B Wallet Action Failed"),
				indicator: "red",
				message: r.message?.message || __("The C2B wallet action could not be completed."),
			});
			frm.reload_doc();
		},
	});
};

frappe.songa_wallet_c2b.open_link_dialog = (frm) => {
	const dialog = new frappe.ui.Dialog({
		title: __("Link C2B Payment"),
		size: "large",
		fields: [
			{
				fieldtype: "Data",
				fieldname: "full_name",
				label: __("Full Name"),
			},
			{
				fieldtype: "Data",
				fieldname: "transid",
				label: __("Trans ID"),
			},
			{
				fieldtype: "Float",
				fieldname: "amount",
				label: __("Amount"),
				default: frm.doc.amount,
			},
			{
				fieldtype: "Button",
				fieldname: "search",
				label: __("Search"),
			},
			{
				fieldtype: "HTML",
				fieldname: "results",
			},
		],
		primary_action_label: __("Link Selected"),
		primary_action() {
			if (!dialog.selected_c2b) {
				frappe.msgprint(__("Select a C2B payment from the results."));
				return;
			}

			frappe.songa_wallet_c2b.call(
				"link_mpesa_c2b_to_wallet",
				{
					wallet_doctype: frm.doctype,
					wallet_name: frm.doc.name,
					c2b_name: dialog.selected_c2b,
				},
				frm,
				__("C2B payment linked.")
			);
			dialog.hide();
		},
	});

	dialog.selected_c2b = null;
	dialog.fields_dict.search.$input.on("click", () => {
		frappe.songa_wallet_c2b.run_search(dialog);
	});

	dialog.show();
	// Field defaults are not always available via get_value() until set after show.
	if (frm.doc.amount != null && frm.doc.amount !== "") {
		dialog.set_value("amount", frm.doc.amount);
	}
	frappe.songa_wallet_c2b.run_search(dialog, { amount: frm.doc.amount });
};

frappe.songa_wallet_c2b.run_search = (dialog, fallback = {}) => {
	const full_name = dialog.get_value("full_name") || fallback.full_name;
	const transid = dialog.get_value("transid") || fallback.transid;
	const amount =
		dialog.get_value("amount") ??
		(fallback.amount !== undefined && fallback.amount !== null && fallback.amount !== ""
			? fallback.amount
			: null);

	if (!full_name && !transid && (amount === undefined || amount === null || amount === "")) {
		frappe.msgprint(__("Provide at least one of Full Name, Trans ID, or Amount."));
		return;
	}

	frappe.call({
		method: `${frappe.songa_wallet_c2b.UTILS}.search_mpesa_c2b_for_wallet_link`,
		args: {
			full_name,
			transid,
			amount,
			limit: 20,
		},
		callback(r) {
			const rows = r.message?.data || [];
			const wrapper = dialog.fields_dict.results.$wrapper;
			dialog.selected_c2b = null;
			if (!rows.length) {
				wrapper.html(`<p class="text-muted">${__("No matching C2B payments found.")}</p>`);
				return;
			}

			const table_rows = rows
				.map(
					(row) => `
				<tr data-name="${frappe.utils.escape_html(row.name)}" style="cursor:pointer;">
					<td>${frappe.utils.escape_html(row.name || "")}</td>
					<td>${frappe.utils.escape_html(row.transid || "")}</td>
					<td>${frappe.utils.escape_html(row.full_name || "")}</td>
					<td>${frappe.format(row.transamount, { fieldtype: "Float" })}</td>
					<td>${frappe.utils.escape_html(row.transtime || "")}</td>
					<td>${frappe.utils.escape_html(row.msisdn || "")}</td>
				</tr>`
				)
				.join("");

			wrapper.html(`
				<table class="table table-bordered table-hover">
					<thead>
						<tr>
							<th>${__("Name")}</th>
							<th>${__("Trans ID")}</th>
							<th>${__("Full Name")}</th>
							<th>${__("Amount")}</th>
							<th>${__("Trans Time")}</th>
							<th>${__("MSISDN")}</th>
						</tr>
					</thead>
					<tbody>${table_rows}</tbody>
				</table>
			`);

			wrapper.find("tr[data-name]").on("click", function () {
				wrapper.find("tr").removeClass("table-active");
				$(this).addClass("table-active");
				dialog.selected_c2b = $(this).attr("data-name");
			});
		},
	});
};

frappe.songa_wallet_c2b.setup_form = (frm) => {
	if (
		frm.is_new() ||
		frm.doc.docstatus !== 1 ||
		frm.doc.transaction_type !== "Recharge" ||
		frm.doc.driver_commission_ledger ||
		frm.doc.mpesa_express_request
	) {
		return;
	}

	if (!frm.doc.mpesa_c2b_payment_register) {
		if (frm.doc.status === "In Progress") {
			frm.add_custom_button(__("Link C2B Payment"), () => {
				frappe.songa_wallet_c2b.open_link_dialog(frm);
			});
		}
		return;
	}

	if (frm.doc.status === "In Progress") {
		frm.add_custom_button(__("Unlink C2B Payment"), () => {
			frappe.confirm(__("Unlink the C2B payment from this recharge?"), () => {
				frappe.songa_wallet_c2b.call(
					"unlink_mpesa_c2b_from_wallet",
					{
						wallet_doctype: frm.doctype,
						wallet_name: frm.doc.name,
					},
					frm,
					__("C2B payment unlinked.")
				);
			});
		});

		frm.add_custom_button(__("Complete Wallet Recharge"), () => {
			frappe.confirm(
				__("Complete this wallet recharge using the linked C2B payment?"),
				() => {
					frappe.songa_wallet_c2b.call(
						"process_mpesa_c2b_wallet_payment",
						{
							wallet_doctype: frm.doctype,
							wallet_name: frm.doc.name,
						},
						frm,
						__("Wallet recharge completed.")
					);
				}
			);
		});
	}
};
