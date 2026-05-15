# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    enable_past_due_notification = fields.Boolean(
        string="Past Due Notification on E-Commerce",
        help="Show customer's past due invoice balance during website checkout.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    enable_past_due_notification = fields.Boolean(
        related="company_id.enable_past_due_notification",
        readonly=False,
        string="Past Due Notification on E-Commerce",
    )


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _send_invoice(self):
        for tx in self:
            is_past_due_payment = tx.invoice_ids and not any(
                inv.line_ids.sale_line_ids for inv in tx.invoice_ids
            )
            if is_past_due_payment:
                return
        return super()._send_invoice()