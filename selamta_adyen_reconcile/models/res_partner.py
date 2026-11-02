from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    selamta_ach_blocked = fields.Boolean(
        'ACH payments turned off', tracking=True, copy=False,
        help='Tick to stop this customer paying by ACH (bank account) online or with a saved bank account; untick '
             'to allow it again. Ticked automatically after the third chargeback incident in 12 months, unless '
             '"Turn ACH off automatically" is unticked.')
    selamta_ach_blocked_note = fields.Char('Why ACH is off', copy=False)
    selamta_ach_auto_off = fields.Boolean(
        'Turn ACH off automatically', default=True, tracking=True,
        help='Ticked: ACH is turned off automatically from the third chargeback incident in 12 months. '
             'Untick for a customer who should keep ACH whatever happens; their chargebacks are still booked, '
             'emailed and charged the fee as usual.')
    selamta_dispute_ids = fields.One2many('selamta.adyen.dispute', 'partner_id', string='Adyen chargebacks')

    def _selamta_ach_blocked(self):
        """True when this partner's company has ACH turned off."""
        self.ensure_one()
        return bool(self.sudo().commercial_partner_id.selamta_ach_blocked)
