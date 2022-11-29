# This software and associated files (the “Software”) can only be used (executed)
# with a valid Numla Enterprise Subscription for the correct number of users.
# It is forbidden to modify, publish, distribute, sublicense,
# or sell copies of the Software or modified copies of the Software.
#
# See LICENSE for full licensing information.
# Copyright (c) 2022 Numla Limited <az@numla.com>
# All rights reserved.
from odoo import fields, models, api


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    removal_sequence = fields.Integer(related="location_id.removal_sequence", store=True)

    @api.model
    def _get_removal_strategy_order(self, removal_strategy):
        res = super(StockQuant, self)._get_removal_strategy_order(removal_strategy)
        move = self._context.get('move', False)
        if move and move[0].picking_type_id.is_remove_closet_location:
            return 'removal_sequence ASC'
        return res
