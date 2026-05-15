# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApproveCreditLimit(models.TransientModel):
    _name = "approval.credit.limit"
    _description = "Credit limit Approval"

    approved_amount = fields.Float(
        string="Approved Amount", copy=False, help="Approval amount."
    )
    reason = fields.Text(
        string="Reason", help="Reason to approve amount for this order or invoice."
    )

    @api.model
    def default_get(self, fields):
        res = super(ApproveCreditLimit, self).default_get(fields)
        active_id = self.env.context.get("active_id")
        active_model = self.env.context.get("active_model")
        if active_id and active_model == "sale.order":
            order_id = self.env["sale.order"].browse(active_id)
            res["approved_amount"] = order_id.amount_total
        elif active_id and active_model == "account.move":
            invoice_id = self.env["account.move"].browse(active_id)
            res["approved_amount"] = invoice_id.amount_total
        return res

    def approved_credit_limit(self):
        active_id = self.env.context.get("active_id")
        active_model = self.env.context.get("active_model")

        if active_id and active_model == "sale.order":
            order_id = self.env["sale.order"].browse(active_id)
            if self.approved_amount > order_id.amount_total:
                raise UserError(
                    _("Approval amount must be equal or less than %s")
                    % order_id.amount_total
                )
            elif self.approved_amount <= 0:
                raise UserError(_("Approval amount must be positive."))
            else:
                order_id.state = "approved"
                order_id.approved_amount = self.approved_amount
                order_id.upgrade_approval = True
                order_id.write(
                    {
                        "approval_history_ids": [
                            (
                                0,
                                0,
                                {
                                    "approved_amount": self.approved_amount,
                                    "reason": self.reason,
                                    "status": "approved",
                                    "order_id": order_id.id,
                                },
                            )
                        ]
                    }
                )

        if active_id and active_model == "account.move":
            invoice_id = self.env["account.move"].browse(active_id)
            if self.approved_amount > invoice_id.amount_total:
                raise UserError(
                    _("Approval amount must be equal or less than %s ")
                    % (invoice_id.amount_total)
                )
            elif self.approved_amount <= 0:
                raise UserError(_("Approval amount must be positive."))
            else:
                invoice_id.state = "approved"
                invoice_id.inv_approved_amount = self.approved_amount
                # invoice_id.upgrade_approval = True
                invoice_id.write(
                    {
                        "inv_approval_history_ids": [
                            (
                                0,
                                0,
                                {
                                    "approved_amount": self.approved_amount,
                                    "reason": self.reason,
                                    "status": "approved",
                                    "invoice_id": invoice_id.id,
                                },
                            )
                        ]
                    }
                )
                # so action_post() skips the credit check this time
                invoice_id.with_context(by_pass_credit_check=True).action_post()

        return True

    def cancel_credit_limit(self):
        active_id = self.env.context.get("active_id")
        active_model = self.env.context.get("active_model")
        if active_id and active_model == "sale.order":
            order_id = self.env["sale.order"].browse(active_id)
            order_id.state = "cancel"
            order_id.write(
                {
                    "approval_history_ids": [
                        (
                            0,
                            0,
                            {
                                "reason": self.reason,
                                "status": "rejected",
                                "order_id": order_id.id,
                            },
                        )
                    ]
                }
            )
            message = "Reject Message" + " : " + self.reason
            order_id.message_post(body=message)

        if active_id and active_model == "account.move":
            invoice_id = self.env["account.move"].browse(active_id)
            invoice_id.state = "cancel"
            invoice_id.write(
                {
                    "inv_approval_history_ids": [
                        (
                            0,
                            0,
                            {
                                "reason": self.reason,
                                "status": "rejected",
                                "invoice_id": invoice_id.id,
                            },
                        )
                    ]
                }
            )
            message = "Reject Message" + " : " + self.reason
            invoice_id.message_post(body=message)

        return True
