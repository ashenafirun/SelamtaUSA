# This software and associated files (the “Software”) can only be used (executed)
# with a valid Numla Enterprise Subscription for the correct number of users.
# It is forbidden to modify, publish, distribute, sublicense,
# or sell copies of the Software or modified copies of the Software.
#
# See LICENSE for full licensing information.
# Copyright (c) 2022 Numla Limited <az@numla.com>
# All rights reserved.
from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    is_remove_closet_location = fields.Boolean(string="Remove From Closet Location?")
