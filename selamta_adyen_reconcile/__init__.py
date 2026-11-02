from . import controllers
from . import models
from . import tools
from . import wizard


def _post_init_hook(env):
    """Turn automatic processing on and pre-fill Selamta's accounts where they exist."""
    params = env['ir.config_parameter'].sudo()
    if not params.get_param('selamta_adyen_reconcile.auto_process'):
        params.set_param('selamta_adyen_reconcile.auto_process', 'True')
    for company in env['res.company'].search([]):
        Account = env['account.account'].with_company(company)
        vals = {}
        if not company.adyen_rec_journal_id:
            journal = env['account.journal'].search(
                [('company_id', '=', company.id), ('type', '=', 'bank'), ('code', '=', 'BNK1')], limit=1)
            vals['adyen_rec_journal_id'] = journal.id
        if not company.adyen_rec_fee_account_id:
            vals['adyen_rec_fee_account_id'] = Account.search([('code', '=', '500002')], limit=1).id
        if not company.adyen_rec_deposit_account_id:
            vals['adyen_rec_deposit_account_id'] = Account.search([('code', '=', '143000')], limit=1).id
        vals = {k: v for k, v in vals.items() if v}
        if vals:
            company.write(vals)
    _set_chargeback_defaults(env)


def _set_chargeback_defaults(env):
    """Point chargeback alerts at the "office" channel and the fee at "Chargeback payment fee", if they exist.

    Called on install and by the 18.0.1.1.0 upgrade.
    """
    channel = env['discuss.channel'].search([('channel_type', '=', 'channel'), ('name', '=ilike', 'office')], limit=1)
    product = env['product.product'].search([('name', '=ilike', 'chargeback payment fee')], limit=1)
    for company in env['res.company'].search([]):
        vals = {}
        if not company.adyen_rec_dispute_channel_id and channel:
            vals['adyen_rec_dispute_channel_id'] = channel.id
        if not company.adyen_rec_cb_fee_product_id and product:
            vals['adyen_rec_cb_fee_product_id'] = product.id
        if vals:
            company.write(vals)
