from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    selamta_ach_blocked = fields.Boolean(
        'ACH payments turned off', tracking=True, copy=False,
        help='Set automatically after the third chargeback incident in 12 months. While set, this customer '
             'cannot pay by ACH (bank account) online or with a saved bank account.')
    selamta_ach_blocked_note = fields.Char('Why ACH is off', copy=False)
    selamta_dispute_ids = fields.One2many('selamta.adyen.dispute', 'partner_id', string='Adyen chargebacks')

    def _selamta_ach_blocked(self):
        """True when this partner's company has ACH turned off."""
        self.ensure_one()
        return bool(self.sudo().commercial_partner_id.selamta_ach_blocked)
