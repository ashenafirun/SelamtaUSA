# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .ltl_common import FREIGHT_CLASSES


class LtlDensityScale(models.Model):
    """Density (pounds per cubic foot) to freight class.

    Lines without an NMFC item are the general NMFC density scale. Lines with an NMFC item
    apply only to that item and replace the general scale for it (some items have their
    own subs).
    """
    _name = 'selamta.ltl.density.scale'
    _description = 'Freight density scale'
    _order = 'nmfc_item, min_density desc'

    nmfc_item = fields.Char(
        'NMFC item', help='Leave empty for the general scale. Fill in to give one NMFC item '
                          'its own density subs.')
    min_density = fields.Float(
        'From density (lb/ft³)', required=True, digits=(16, 2),
        help='This class applies from this density up to the next line\'s density.')
    freight_class = fields.Selection(FREIGHT_CLASSES, 'Class', required=True)
    note = fields.Char('Note')

    @api.model
    def _class_for_density(self, density, nmfc_item=False):
        """Freight class for a density, using the NMFC item's own scale when it has one."""
        if not density or density <= 0:
            return False
        lines = self.browse()
        if nmfc_item:
            lines = self.search([('nmfc_item', '=', nmfc_item.strip())])
        if not lines:
            lines = self.search([('nmfc_item', '=', False)])
        best = False
        for line in lines.sorted('min_density'):
            if density + 1e-9 >= line.min_density:
                best = line.freight_class
        return best
