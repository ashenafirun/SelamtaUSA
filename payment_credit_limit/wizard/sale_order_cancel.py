from odoo import models


class SaleOrderCancel(models.TransientModel):
    _inherit = "sale.order.cancel"

    def action_send_mail_and_cancel(self):
        res = super(SaleOrderCancel, self).action_send_mail_and_cancel()
        self.order_id.already_delivery_generated = False
        if self.order_id.picking_ids:
            latest_picking = max(self.order_id.picking_ids, key=lambda p: p.create_date)
            if latest_picking.state == "done":
                self.order_id.already_delivery_generated = False
        return res

    def action_cancel(self):
        res = super(SaleOrderCancel, self).action_cancel()
        self.order_id.already_delivery_generated = False
        if self.order_id.picking_ids:
            latest_picking = max(self.order_id.picking_ids, key=lambda p: p.create_date)
            if latest_picking.state == "done":
                self.order_id.already_delivery_generated = False
        return res
