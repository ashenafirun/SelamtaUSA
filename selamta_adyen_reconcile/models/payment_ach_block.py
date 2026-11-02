"""Turn ACH off for customers flagged after repeated chargebacks.

Three places: the payment methods offered online, the saved bank accounts offered online, and a last
check when any transaction is created (which also covers staff charging a saved bank account from
the back office). Refunds are never blocked.
"""
from odoo import _, api, models
from odoo.exceptions import UserError

ACH_CODE = 'ach_direct_debit'


def _is_ach_method(method):
    return ACH_CODE in {method.code, method.primary_payment_method_id.code}


def _partner_blocked(env, partner_id):
    partner = env['res.partner'].browse(partner_id).exists() if partner_id else env['res.partner']
    return bool(partner) and partner._selamta_ach_blocked()


class PaymentMethod(models.Model):
    _inherit = 'payment.method'

    @api.model
    def _get_compatible_payment_methods(self, provider_ids, partner_id, *args, **kwargs):
        methods = super()._get_compatible_payment_methods(provider_ids, partner_id, *args, **kwargs)
        if _partner_blocked(self.env, partner_id):
            methods = methods.filtered(lambda m: not _is_ach_method(m))
        return methods


class PaymentToken(models.Model):
    _inherit = 'payment.token'

    @api.model
    def _get_available_tokens(self, providers_ids, partner_id, *args, **kwargs):
        tokens = super()._get_available_tokens(providers_ids, partner_id, *args, **kwargs)
        if _partner_blocked(self.env, partner_id):
            tokens = tokens.filtered(lambda t: not _is_ach_method(t.payment_method_id))
        return tokens


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    @api.model_create_multi
    def create(self, vals_list):
        transactions = super().create(vals_list)
        for tx in transactions:
            if tx.operation in ('refund', 'validation') or not tx.partner_id:
                continue
            method = tx.payment_method_id or tx.token_id.payment_method_id
            if _is_ach_method(method) and tx.partner_id._selamta_ach_blocked():
                raise UserError(_(
                    'ACH payments are turned off for %s after repeated returned payments. Use another payment '
                    'method, or turn ACH back on in the customer\'s Chargebacks tab.',
                    tx.partner_id.commercial_partner_id.display_name))
        return transactions
