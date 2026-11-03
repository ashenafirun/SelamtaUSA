# -*- coding: utf-8 -*-
"""UPS from the LTL shipment: fix our "Parcel box 20x12x12" package type.

It was made for the old UPS connector (carrier type "ups") with its sizes in the database's
length unit (1.67 x 1 x 1 ft), so it was not offered for the UPS shipping method and UPS
would have read 1.67 x 1 x 1 inches. A UPS package type holds its sizes in inches. Only a
box still exactly as it was created is changed; one someone edited is left alone.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    PackageType = env['stock.package.type']
    box = PackageType.search([('name', '=', 'Parcel box 20x12x12')], limit=1)
    if not box:
        return
    template = env['product.template']
    inch = env.ref('uom.product_uom_inch')
    length_uom = template._get_length_uom_id_from_ir_config_parameter()
    as_created = [round(inch._compute_quantity(v, length_uom, round=False), 4) for v in (20, 12, 12)]
    current = [round(v or 0.0, 4) for v in (box.packaging_length, box.width, box.height)]
    if current != as_created and current != [20.0, 12.0, 12.0]:
        _logger.info('Parcel box was edited (%s); left alone.', current)
        return
    vals = PackageType._ltl_parcel_box_vals()
    vals.pop('name')
    vals.pop('max_weight')
    box.write(vals)
    _logger.info('Parcel box set up for UPS: %s', vals)
