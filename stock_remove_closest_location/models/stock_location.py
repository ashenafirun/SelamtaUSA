# This software and associated files (the “Software”) can only be used (executed)
# with a valid Numla Enterprise Subscription for the correct number of users.
# It is forbidden to modify, publish, distribute, sublicense,
# or sell copies of the Software or modified copies of the Software.
#
# See LICENSE for full licensing information.
# Copyright (c) 2022 Numla Limited <az@numla.com>
# All rights reserved.
from odoo import api, fields, models
from odoo.osv import expression


class Location(models.Model):
    _inherit = 'stock.location'

    removal_sequence = fields.Integer(default=1)

    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        if operator == 'ilike' and not name.strip():
            domain = []
        elif operator in expression.NEGATIVE_TERM_OPERATORS:
            domain = [('barcode', operator, name), ('complete_name', operator, name)]
        else:
            domain = ['|', ('barcode', operator, name), ('complete_name', operator, name)]
        return self._search(expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid,
                            order='removal_sequence asc')
