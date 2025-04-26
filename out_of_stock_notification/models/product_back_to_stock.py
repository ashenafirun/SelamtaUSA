from odoo import models, fields, _
from odoo.http import request


class ProductBackToStock(models.Model):
    _name = 'product.back.to.stock'

    user_id = fields.Many2one('res.users', string='User')
    product_id = fields.Many2one('product.product', string='Product')
    stock_notification = fields.Boolean(default=True)

    def is_in_list(self, product_id=None):
        if product_id:
            in_list = self.search([('product_id', '=', int(product_id)),
                                   ('user_id', '=', request.env.user.id)])
            return len(in_list) > 0
        return False

    def _send_availability_email(self):
        to_notify = self.env['product.back.to.stock'].search([('stock_notification', '=', True)])

        notified = self.env['product.back.to.stock']

        # tmpl = self.env.ref("out_of_stock_notification.availability_email_body_stock_back")
        for rec in to_notify:
            product = rec.product_id
            if not product._is_sold_out():
                body_html = self.env['ir.qweb']._render("out_of_stock_notification.availability_email_body_stock_back" ,{"wishlist": rec, "company": self.env.company})
                msg = self.env["mail.message"].sudo().new(dict(body=body_html, record_name=product.name))
                full_mail = self.env["mail.render.mixin"]._render_encapsulate(
                    "mail.mail_notification_light",
                    body_html,
                    add_context=dict(message=msg, model_description=_("Wishlist")),
                )
                mail_values = {
                    "subject": _("The product '%(product_name)s' is now available") % {'product_name': product.name},
                    "email_from": (product.company_id.partner_id or self.env.user).email_formatted,
                    "email_to": rec.user_id.partner_id.email_formatted,
                    "body_html": full_mail,
                }

                mail = self.env["mail.mail"].sudo().create(mail_values)
                mail.send(raise_exception=False)
                notified += rec
        notified.stock_notification = False
