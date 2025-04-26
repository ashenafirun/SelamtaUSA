# -*- coding: utf-8 -*-

import json
from odoo import api, fields, models

class BlogPost(models.Model):
    _inherit = "blog.post"

    cover_background = fields.Char(compute="_get_background_image")

    @api.depends('cover_properties')
    def _get_background_image(self):
        for i in self:
            cover_properties = json.loads(i.cover_properties)
            i.cover_background = cover_properties['background-image']