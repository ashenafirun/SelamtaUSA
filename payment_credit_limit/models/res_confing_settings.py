# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _

class ResCompany(models.Model):
    _inherit = "res.company"

    override_credit_limit_approval = fields.Boolean(
        string="Override Credit Limit Approval or Reject Rule",
        help="Allow users to bypass credit limit approval or reject restrictions.",
    )

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"


    override_credit_limit_approval = fields.Boolean(
        related="company_id.override_credit_limit_approval",
        readonly=False,
    )