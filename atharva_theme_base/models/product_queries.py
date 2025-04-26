# -*- coding: utf-8 -*-

import json
import re

from odoo import fields, models, api
from odoo.tools.translate import html_translate
from odoo.exceptions import UserError, ValidationError

class User(models.Model):
    _inherit = 'res.users'

    inquiry_data = fields.Text("Inquiry Data", store=True, default="{}")

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    active_product_inquiry = fields.Boolean(string="Inquiry Submit Action",related='website_id.active_product_inquiry',readonly=False)
    inquiry_submit_action = fields.Selection(
        selection=[('email', "Send An Email"),('crm', "Create An Opportunity")], string="Product Queries Action", related="website_id.inquiry_submit_action", readonly=False)
    inquiry_recipient_id = fields.Many2one('res.users',related='website_id.inquiry_recipient_id',domain="[('share', '=', False)]",readonly=False)
    sales_person_id = fields.Many2one('res.users', related='website_id.sales_person_id', string='Salesperson', readonly=False, domain="[('share', '=', False)]")
    sales_team_id = fields.Many2one('crm.team', related='website_id.sales_team_id', string='Sales Team', readonly=False)
    inquiry_header = fields.Text("Inquery Header",  related="website_id.inquiry_header", readonly=False, translate=True)
    inquiry_desc_info = fields.Text("Inquery Information", related="website_id.inquiry_desc_info", readonly=False, translate=True)
    acknowledgement_message = fields.Text("Acknowledgement Message", related="website_id.acknowledgement_message", readonly=False, translate=True)

class CustomWebsite(models.Model):
    _inherit = 'website'

    def _default_sales_team_id(self):
        team = self.env.ref('sales_team.salesteam_website_sales', False)
        if team and team.active:
            return team.id
        else:
            return None

    inquiry_submit_action = fields.Selection(
        selection=[('email', "Send An Email"),('crm', "Create An Opportunity")],string="Product Queries Action")
    sales_person_id = fields.Many2one('res.users', string='Salesperson')
    sales_team_id = fields.Many2one('crm.team',string='Sales Team', ondelete="set null",default=_default_sales_team_id)
    inquiry_recipient_id = fields.Many2one('res.users',string="Inquiry Recipient")
    inquiry_header = fields.Text("Inquery Header", default="Have Questions ?", translate=True)
    inquiry_desc_info = fields.Text("Inquery Information", default="We will follow up with you via email within 24-56 hours", translate=True)
    acknowledgement_message = fields.Text("Acknowledgement Message", default="Thank You", translate=True)
