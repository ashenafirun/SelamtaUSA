from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    adyen_rec_journal_id = fields.Many2one(
        'account.journal', string='Adyen payout bank journal', domain=[('type', '=', 'bank')])
    adyen_rec_fee_account_id = fields.Many2one('account.account', string='Adyen fees account')
    adyen_rec_deposit_account_id = fields.Many2one('account.account', string='Adyen deposit account')
    adyen_rec_review_user_id = fields.Many2one('res.users', string='Adyen review user')
