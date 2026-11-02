from odoo import SUPERUSER_ID, api

from odoo.addons.selamta_adyen_reconcile import _set_chargeback_defaults


def migrate(cr, version):
    """Chargeback handling arrives in 18.0.1.1.0: fill in the office channel and the fee product."""
    _set_chargeback_defaults(api.Environment(cr, SUPERUSER_ID, {}))
