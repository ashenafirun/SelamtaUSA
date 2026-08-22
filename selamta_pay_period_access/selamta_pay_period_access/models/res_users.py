from odoo import models

PAY_PERIOD_FIELDS = ['x_hours_current_pay_period']


class ResUsers(models.Model):
    _inherit = 'res.users'

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + PAY_PERIOD_FIELDS
