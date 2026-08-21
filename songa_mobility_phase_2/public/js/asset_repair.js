const should_show_check_stock_balance = (frm) => {
	return (
		frm.doc.docstatus === 0 &&
		cint(frm.doc.stock_consumption) === 1 &&
		(frm.doc.stock_items || []).length > 0
	);
};

const fetch_stock_balance = (item_code, warehouse) => {
	return new Promise((resolve) => {
		frappe.call({
			method: "erpnext.stock.utils.get_stock_balance",
			args: { item_code, warehouse },
			callback(r) {
				resolve({
					ok: true,
					balance: flt(r.message),
				});
			},
			error(r) {
				resolve({
					ok: false,
					error:
						(r && r.message) ||
						__("Could not fetch stock balance for {0} in {1}", [item_code, warehouse]),
				});
			},
		});
	});
};

const build_stock_balance_rows = async (stock_items) => {
	const tasks = (stock_items || []).map(async (item) => {
		const item_code = item.item_code;
		const warehouse = item.warehouse;
		const required = flt(item.consumed_quantity);

		if (!item_code || !warehouse) {
			return {
				item_code: item_code || __("(missing item)"),
				warehouse: warehouse || __("(missing warehouse)"),
				required,
				available: null,
				status: __("Incomplete"),
				ok: false,
			};
		}

		const result = await fetch_stock_balance(item_code, warehouse);
		if (!result.ok) {
			return {
				item_code,
				warehouse,
				required,
				available: null,
				status: __("Error"),
				ok: false,
				error: result.error,
			};
		}

		const available = result.balance;
		const sufficient = available >= required;
		return {
			item_code,
			warehouse,
			required,
			available,
			status: sufficient ? __("OK") : __("Short"),
			ok: sufficient,
		};
	});

	return Promise.all(tasks);
};

const format_qty = (value) => {
	if (value === null || value === undefined) {
		return "—";
	}
	return format_number(value);
};

const show_stock_balance_dialog = (rows) => {
	const table_rows = rows
		.map((row) => {
			const color = row.ok ? "green" : "red";
			const detail = row.error
				? `<br><small class="text-muted">${frappe.utils.escape_html(
						String(row.error)
				  )}</small>`
				: "";
			return `<tr>
				<td>${frappe.utils.escape_html(row.item_code)}</td>
				<td>${frappe.utils.escape_html(row.warehouse)}</td>
				<td class="text-right">${format_qty(row.required)}</td>
				<td class="text-right">${format_qty(row.available)}</td>
				<td><span class="indicator-pill ${color} filter">${frappe.utils.escape_html(
				row.status
			)}</span>${detail}</td>
			</tr>`;
		})
		.join("");

	const dialog = new frappe.ui.Dialog({
		title: __("Stock Balance"),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "stock_balance_html",
			},
		],
	});

	dialog.fields_dict.stock_balance_html.$wrapper.html(`
		<div class="table-responsive">
			<table class="table table-bordered">
				<thead>
					<tr>
						<th>${__("Item")}</th>
						<th>${__("Warehouse")}</th>
						<th class="text-right">${__("Required")}</th>
						<th class="text-right">${__("Available")}</th>
						<th>${__("Status")}</th>
					</tr>
				</thead>
				<tbody>${table_rows}</tbody>
			</table>
		</div>
	`);

	dialog.show();
};

const check_stock_balance = async (frm) => {
	const stock_items = frm.doc.stock_items || [];
	if (!stock_items.length) {
		frappe.msgprint({
			title: __("Check Stock Balance"),
			indicator: "orange",
			message: __("Add stock items before checking balance."),
		});
		return;
	}

	frappe.dom.freeze(__("Checking stock balance..."));
	try {
		const rows = await build_stock_balance_rows(stock_items);
		show_stock_balance_dialog(rows);
	} finally {
		frappe.dom.unfreeze();
	}
};

const toggle_check_stock_balance_button = (frm) => {
	frm.remove_custom_button(__("Check Stock Balance"));

	if (!should_show_check_stock_balance(frm)) {
		return;
	}

	frm.add_custom_button(__("Check Stock Balance"), () => {
		check_stock_balance(frm);
	});
};

frappe.ui.form.on("Asset Repair", {
	refresh(frm) {
		toggle_check_stock_balance_button(frm);
	},
	stock_consumption(frm) {
		toggle_check_stock_balance_button(frm);
	},
});

frappe.ui.form.on("Asset Repair Consumed Item", {
	stock_items_add(frm) {
		toggle_check_stock_balance_button(frm);
	},
	stock_items_remove(frm) {
		toggle_check_stock_balance_button(frm);
	},
});
