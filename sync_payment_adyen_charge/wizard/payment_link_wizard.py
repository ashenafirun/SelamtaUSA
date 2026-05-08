# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.

from odoo import models


class PaymentLinkWizard(models.TransientModel):
    _inherit = "payment.link.wizard"

    def _prepare_query_params(self, related_document):
        params = super()._prepare_query_params(related_document)
        invoice = self.env["account.move"].browse(self.env.context.get("active_id"))
        is_installment = False
        if self.amount < invoice.amount_residual:
            is_installment = True
        params.update(
            {
                "move_id": invoice.id,
                "amount": self.amount,
                "payment": True,
                "is_installment": 1 if is_installment else 0,
            }
        )
        return params
