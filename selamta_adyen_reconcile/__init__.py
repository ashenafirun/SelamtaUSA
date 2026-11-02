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
