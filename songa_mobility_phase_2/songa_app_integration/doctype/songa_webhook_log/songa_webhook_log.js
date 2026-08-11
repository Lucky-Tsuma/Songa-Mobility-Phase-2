const callWebhookAction = (method, frm, successMessage) => {
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
				title: __("Webhook Action Failed"),
				indicator: "red",
				message: r.message?.message || __("The webhook action could not be completed."),
			});
			frm.reload_doc();
		},
	});
};

frappe.ui.form.on("Songa Webhook Log", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		if (frm.doc.status === "Failed") {
			frm.add_custom_button(__("Retry"), () => {
				callWebhookAction(
					"songa_mobility_phase_2.songa_app_integration.utils.songa_webhook.retry_songa_webhook_log_from_desk",
					frm,
					__("Webhook sent successfully.")
				);
			});

			frm.add_custom_button(
				__("Abandon"),
				() => {
					frappe.confirm(__("Mark this webhook log as Abandoned?"), () => {
						callWebhookAction(
							"songa_mobility_phase_2.songa_app_integration.utils.songa_webhook.abandon_songa_webhook_log",
							frm,
							__("Webhook log marked as Abandoned.")
						);
					});
				},
				__("Actions")
			);
		}

		if (frm.doc.status === "Abandoned") {
			frm.add_custom_button(__("Retry"), () => {
				callWebhookAction(
					"songa_mobility_phase_2.songa_app_integration.utils.songa_webhook.retry_songa_webhook_log_from_desk",
					frm,
					__("Webhook sent successfully.")
				);
			});
		}
	},
});
