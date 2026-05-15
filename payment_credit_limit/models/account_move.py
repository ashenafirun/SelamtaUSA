# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    state = fields.Selection(
        selection_add=[("credit_hold", "CC Hold"), ("approved", "Approved")],
        ondelete={
            "credit_hold": "set default",
            "approved": "set default",
        },
    )

    inv_approval_history_ids = fields.One2many(
        "orderline.approval.history", "invoice_id", string="Approval History"
    )
    inv_approved_amount = fields.Float(string="Approved Amount", copy=False)

    def action_post(self):
        # If the entire batch is bypassing credit check, post everything at once
        if self.env.context.get("by_pass_credit_check"):
            return super().action_post()

        moves_to_post = self.env["account.move"]

        for move in self:
            # Invoices linked to confirmed sale orders skip the credit check
            if move.invoice_line_ids.mapped("sale_line_ids"):
                moves_to_post |= move
                continue
            if move.move_type == "out_invoice" and move.partner_id.credit_limit > 0.0:
                check_false, cc_hold = self.env["credit.code"].check_approval_status(move=move)
                if cc_hold:
                    move.state = "credit_hold"
                    move.invoice_date = fields.Date.today()
                    continue
                if (
                    not check_false
                    and move.amount_total > move.partner_id.remaining_credit_limit
                ):
                    move.state = "credit_hold"
                    move.invoice_date = fields.Date.today()
                    move.message_post(
                        body=_(
                            "Invoice placed on Credit Hold: amount exceeds the partner's remaining credit limit."
                        )
                    )
                    continue
            moves_to_post |= move

        if moves_to_post:
            return super(AccountMove, moves_to_post).action_post()
        return False

    def button_draft(self):
        res = super().button_draft()
        self.write(
            {
                "inv_approved_amount": 0.0,
            }
        )
        return res

    def credit_approve_invoice(self):
        """Open approval wizard for manager to approve the invoice."""
        if not self.env.user.has_group(
            "sales_team.group_sale_manager"
        ) and not self.env.user.has_group("account.group_account_manager"):
            raise UserError(
                _(
                    "Only users with '%(sale_manager)s' or '%(account_manager)s' rights are allowed to give approval!",
                    sale_manager=self.env.ref(
                        "sales_team.group_sale_manager"
                    ).display_name,
                    account_manager=self.env.ref(
                        "account.group_account_manager"
                    ).display_name,
                )
            )
        view_id = self.env.ref("payment_credit_limit.view_approval_credit_limit", False)
        return {
            "type": "ir.actions.act_window",
            "name": _("Credit Limit Approval"),
            "view_type": "form",
            "view_mode": "form",
            "res_model": "approval.credit.limit",
            "target": "new",
            "views": [(view_id.id if view_id else False, "form")],
            "view_id": view_id.id if view_id else False,
        }

    def cancel_invoice_on_cc(self):
        """Open rejection wizard for manager to reject the invoice."""
        if not self.env.user.has_group(
            "sales_team.group_sale_manager"
        ) and not self.env.user.has_group("account.group_account_manager"):
            raise UserError(
                _(
                    "Only users with '%(sale_manager)s' or '%(account_manager)s' rights are allowed to reject approval requests!",
                    sale_manager=self.env.ref(
                        "sales_team.group_sale_manager"
                    ).display_name,
                    account_manager=self.env.ref(
                        "account.group_account_manager"
                    ).display_name,
                )
            )
        view_id = self.env.ref("payment_credit_limit.view_cancel_credit_limit", False)
        return {
            "type": "ir.actions.act_window",
            "name": _("Cancel Approval"),
            "view_type": "form",
            "view_mode": "form",
            "res_model": "approval.credit.limit",
            "target": "new",
            "views": [(view_id.id if view_id else False, "form")],
            "view_id": view_id.id if view_id else False,
        }

    def action_force_register_payment(self):
        cc_hold_invoices = self.filtered(lambda m: m.state == 'credit_hold')
        if cc_hold_invoices:
            invoice_names = ", ".join(cc_hold_invoices.mapped("name"))
            raise UserError(
                _(
                    "The following invoices are on CC Hold and cannot "
                    "be paid: \n %s",
                    invoice_names,
                )
            )
        return super().action_force_register_payment()
