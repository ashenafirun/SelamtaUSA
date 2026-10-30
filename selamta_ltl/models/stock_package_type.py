# -*- coding: utf-8 -*-
from odoo import fields, models

from .ltl_common import UNIT_TYPES


class StockPackageType(models.Model):
    _inherit = 'stock.package.type'

    ltl_unit_type = fields.Selection(
        UNIT_TYPES, 'LTL handling unit',
        help='How a package of this type goes on the bill of lading (pallet or box). Its '
             'length, width and weight fill in the handling unit; pallet height is measured '
             'per pallet.')
