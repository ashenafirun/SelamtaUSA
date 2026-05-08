# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    credit_limit = fields.Float(
        string="Credit Limit",
        help="Credit limit specific to this partner.",
        groups="account.group_account_invoice,account.group_account_readonly",
        company_dependent=True,
        copy=False,
        readonly=False,
        tracking=True,
    )
    remaining_credit_limit = fields.Float(
        string="Remaining Credit Limit",
        compute="_compute_remaining_credit_limit",
        # store=False kept intentionally: residual amounts change frequently.
        # If performance becomes a concern, set store=True and ensure all
        # relevant account.move state transitions trigger recomputation.
        store=False,
        help="Remaining Credit Limit Amount",
    )

    @api.constrains("credit_limit")
    def _constrains_credit_limit(self):
        for record in self:
            if record.credit_limit < 0.0:
                raise UserError(_("Credit Limit value cannot be negative."))

    def _compute_remaining_credit_limit(self):
        for record in self:
            if record.credit_limit:
                sale_order_amount = sum(record.sale_order_ids.filtered(
                    lambda order: order.state in ['sale', 'approved'] and not order.invoice_ids
                    ).mapped('amount_total'))

                inbound_entry = sum(
                    record.invoice_ids.filtered(
                        lambda inv: inv.state in ["draft", "posted"]
                        and (
                            inv.move_type in ["entry"]
                            and inv.payment_ids
                            and inv.payment_ids.filtered(
                                lambda payment: payment.payment_type == "inbound"
                            )
                        )
                    ).mapped("amount_residual")
                )
                invoiced = sum(
                    record.invoice_ids.filtered(
                        lambda inv: inv.state in ["draft", "posted"]
                        and inv.move_type in ["out_invoice"]
                    ).mapped("amount_residual")
                )
                refund = sum(
                    record.invoice_ids.filtered(
                        lambda inv: inv.state in ["draft", "posted"]
                        and inv.move_type in ["out_refund"]
                    ).mapped("amount_residual")
                )
                invoiced += sale_order_amount
                invoiced += inbound_entry
                if (invoiced - refund) > 0.0:
                    record.remaining_credit_limit = record.credit_limit - (
                        invoiced - refund
                    )
                else:
                    record.remaining_credit_limit = record.credit_limit
            else:
                record.remaining_credit_limit = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        company_limit = self._fields["credit_limit"].get_company_dependent_fallback(
            self
        )
        for vals in vals_list:
            if (
                vals.get("credit_limit", 0)
                and not vals.get("use_partner_credit_limit", False)
                and vals.get("credit_limit", 0) != company_limit
            ):
                vals.update({"use_partner_credit_limit": True})
        return super(ResPartner, self).create(vals_list)
