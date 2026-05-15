# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import models
from . import wizard


def set_credit_limit_boolean(env):
    env["res.company"].sudo().search([]).write({"account_use_credit_limit": True})
    env["ir.config_parameter"].set_param("account.account_use_credit_limit", True)
