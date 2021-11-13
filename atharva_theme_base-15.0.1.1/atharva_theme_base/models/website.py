# -*- coding: utf-8 -*-

from markupsafe import Markup
from odoo import fields, models, api

class CustomWebsite(models.Model):
    _inherit = 'website'

    def get_website_faq_list(self):
        faqs = self.env['faq'].sudo().search([('website_id', 'in', (False, self.get_current_website().id)),
        ('is_published', '=', True)])
        faqs = [{'fid':f.id,'question':f.question, 'answer':Markup(f.answer)} for f in faqs]
        return faqs

class ThemeUtilsExtend(models.AbstractModel):
    _inherit = 'theme.utils'

    @api.model
    def _reset_default_config(self):
        super()._reset_default_config()
        # custom header
        self.disable_view('website.template_header_default')
        self.enable_view('atharva_theme_base.atharva_header')
        # custom footer
        self.disable_view('website.footer_custom')
        self.enable_view('atharva_theme_base.atharva_footer')

class WebsiteMenuAlanTags(models.Model):
    _inherit = "website.menu"

    is_tag_active = fields.Boolean(string="Activate Menu Tag")
    tag_text_color = fields.Char(string="Tag Text Color")
    tag_bg_color = fields.Char(string="Tag Background Color")
    tag_text = fields.Char(string="Tag Text", translate=True)