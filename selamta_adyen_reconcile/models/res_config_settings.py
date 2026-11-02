from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    adyen_rec_api_key = fields.Char(
        'Adyen report API key', config_parameter='selamta_adyen_reconcile.api_key', groups='base.group_system',
        help='API key of an Adyen "Report user" credential with the Merchant Report Download role.')
    adyen_rec_hmac_key = fields.Char(
        'Adyen webhook HMAC key', config_parameter='selamta_adyen_reconcile.hmac_key', groups='base.group_system',
        help='HMAC key of the Adyen webhook that sends "Report available" events to Odoo.')
    adyen_rec_auto_process = fields.Boolean(
        'Reconcile Adyen payouts automatically', config_parameter='selamta_adyen_reconcile.auto_process',
        default=True)
    adyen_rec_journal_id = fields.Many2one(
        related='company_id.adyen_rec_journal_id', readonly=False)
    adyen_rec_fee_account_id = fields.Many2one(
        related='company_id.adyen_rec_fee_account_id', readonly=False)
    adyen_rec_deposit_account_id = fields.Many2one(
        related='company_id.adyen_rec_deposit_account_id', readonly=False)
    adyen_rec_review_user_id = fields.Many2one(
        related='company_id.adyen_rec_review_user_id', readonly=False)
    adyen_rec_dispute_channel_id = fields.Many2one(
        related='company_id.adyen_rec_dispute_channel_id', readonly=False)
    adyen_rec_cb_fee_product_id = fields.Many2one(
        related='company_id.adyen_rec_cb_fee_product_id', readonly=False)
