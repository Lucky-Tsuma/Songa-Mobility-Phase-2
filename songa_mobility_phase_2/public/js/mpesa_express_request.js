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

		const processStatus = frm.doc.custom_songa_wallet_process_status || "Pending";
		const isWalletReference = ["Rental Days", "Energy KWh"].includes(
			frm.doc.reference_doctype
		);
		const isTerminal = ["Completed", "Failed"].includes(frm.doc.status);

		if (!isWalletReference || !isTerminal || frm.doc.custom_songa_wallet_processed) {
			return;
		}

		if (processStatus === "Abandoned") {
			frm.add_custom_button(__("Reset for Retry"), () => {
				frappe.confirm(__("Reset this Abandoned wallet request to Pending?"), () => {
					callMpesaWalletAction(
						"songa_mobility_phase_2.songa_app_integration.utils.utils.reset_mpesa_wallet_processing",
						frm,
						__("M-Pesa wallet processing reset to Pending.")
					);
				});
			});

			frm.add_custom_button(__("Retry Now"), () => {
				callMpesaWalletAction(
					"songa_mobility_phase_2.songa_app_integration.utils.utils.retry_mpesa_wallet_processing",
					frm,
					__("M-Pesa wallet processing completed.")
				);
			});
		}

		if (processStatus === "Pending") {
			frm.add_custom_button(__("Process Wallet"), () => {
				callMpesaWalletAction(
					"songa_mobility_phase_2.songa_app_integration.utils.utils.retry_mpesa_wallet_processing",
					frm,
					__("M-Pesa wallet processing completed.")
				);
			});
		}
	},
});
