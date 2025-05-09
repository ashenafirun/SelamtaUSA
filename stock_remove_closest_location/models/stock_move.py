# This software and associated files (the “Software”) can only be used (executed)
# with a valid Numla Enterprise Subscription for the correct number of users.
# It is forbidden to modify, publish, distribute, sublicense,
# or sell copies of the Software or modified copies of the Software.
#
# See LICENSE for full licensing information.
# Copyright (c) 2022 Numla Limited <az@numla.com>
# All rights reserved.
from odoo import models, fields


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_assign(self,force_qty=False):
        return super(StockMove, self.with_context(move=self))._action_assign(force_qty=force_qty)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    removal_sequence = fields.Integer(string="Removal Sequence",related="location_id.removal_sequence", store=True)
    removal_sequence_display_name = fields.Char(string="Removal Sequence Display Name",related="location_id.display_name", store=True)
