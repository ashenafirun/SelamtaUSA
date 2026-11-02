from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _selamta_is_closed_for_credit(self):
        """True when the order already has a posted customer invoice.

        Selamta does not backorder, so once an order has been invoiced, whatever
        was not invoiced will never be billed and must not count as credit
        exposure. Down payment invoices do not close an order.
        """
        self.ensure_one()
        product_lines = self.order_line.filtered(
            lambda line: not line.display_type and not line.is_downpayment
        )
        return any(
            aml.parent_state == 'posted' and aml.move_id.move_type == 'out_invoice'
            for aml in product_lines.invoice_lines
        )
