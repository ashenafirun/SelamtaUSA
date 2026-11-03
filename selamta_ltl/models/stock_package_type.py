# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.tools import float_round

from .ltl_common import UNIT_TYPES


class StockPackageType(models.Model):
    _inherit = 'stock.package.type'

    ltl_unit_type = fields.Selection(
        UNIT_TYPES, 'LTL handling unit',
        help='How a package of this type goes on the bill of lading (pallet or box). Its '
             'length, width and weight fill in the handling unit; pallet height is measured '
             'per pallet.')

    def _ltl_dimensions(self):
        """(length, width, height) of this package type in inches.

        A package type for a carrier connection (UPS...) holds the sizes exactly as the
        connection sends them to the carrier, in the carrier's unit (inches for UPS here),
        whatever the database's length unit is. Other package types are in the database's
        length unit (feet or millimetres)."""
        self.ensure_one()
        values = (self.packaging_length or 0.0, self.width or 0.0, self.height or 0.0)
        carrier_type = self.package_carrier_type if 'package_carrier_type' in self._fields else False
        if carrier_type and carrier_type != 'none':
            carriers = self.env['delivery.carrier'].sudo()
            if 'ups_package_dimension_unit' in carriers._fields and carriers.search_count([
                    ('delivery_type', '=', carrier_type), ('ups_package_dimension_unit', '=', 'CM')], limit=1):
                return tuple(float_round(value / 2.54, 1) for value in values)
            return tuple(float_round(value, 1) for value in values)
        to_inch = self.env.ref('uom.product_uom_inch')
        length_uom = self.env['product.template']._get_length_uom_id_from_ir_config_parameter()
        return tuple(float_round(length_uom._compute_quantity(value, to_inch, round=False), 1)
                     for value in values)
