from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    adyen_rec_journal_id = fields.Many2one(
        'account.journal', string='Adyen payout bank journal', domain=[('type', '=', 'bank')])
    adyen_rec_fee_account_id = fields.Many2one('account.account', string='Adyen fees account')
    adyen_rec_deposit_account_id = fields.Many2one('account.account', string='Adyen deposit account')
    adyen_rec_review_user_id = fields.Many2one('res.users', string='Adyen review user')
    adyen_rec_dispute_channel_id = fields.Many2one(
        'discuss.channel', string='Chargeback alerts channel', domain=[('channel_type', '=', 'channel')],
        help='Every chargeback is posted here, mentioning each member so it lands in their inbox.')
    adyen_rec_cb_fee_product_id = fields.Many2one(
        'product.product', string='Chargeback fee product',
        help='Invoiced (at its sales price) from the second chargeback incident in 12 months.')
