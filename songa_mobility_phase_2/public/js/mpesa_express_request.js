const callMpesaWalletAction = (method, frm, successMessage) => {
	frappe.call({
		method,
		args: { name: frm.doc.name },
		freeze: true,
		freeze_message: __("Processing..."),
		callback(r) {
			if (r.message?.status === "success") {
				frappe.show_alert({ message: successMessage, indicator: "green" });
				frm.reload_doc();
				return;
			}

			frappe.msgprint({
				title: __("M-Pesa Wallet Action Failed"),
				indicator: "red",
				message: r.message?.message || __("The wallet action could not be completed."),
			});
			frm.reload_doc();
		},
	});
};

frappe.ui.form.on("Mpesa Express Request", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		const isTerminal = ["Completed", "Failed"].includes(frm.doc.status);
		if (!isTerminal) {
			return;
		}

		frm.add_custom_button(__("Process Wallet"), () => {
			callMpesaWalletAction(
				"songa_mobility_phase_2.songa_app_integration.utils.utils.retry_mpesa_wallet_processing",
				frm,
				__("M-Pesa wallet processing completed.")
			);
		});
	},
});
