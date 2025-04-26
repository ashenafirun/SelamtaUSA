from odoo import _, api, fields, models
from odoo.tools import float_compare, float_is_zero, float_repr, float_round, float_split, float_split_str
from odoo.exceptions import UserError

class StockPickingExtended(models.Model):
    _inherit = "stock.picking"


class StockPickingTypeExtended(models.Model):
    _inherit = "stock.picking.type"

    packaging_wise_split = fields.Boolean()

class StockMoveLineExtended(models.Model):
    _inherit = "stock.move.line"
    package_line = fields.Boolean()

class StockMoveExtended(models.Model):
    _inherit = "stock.move"

    def _update_reserved_quantity(self, need, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
        """ Create or update move lines and reserves quantity from quants
            Expects the need (qty to reserve) and location_id to reserve from.
            `quant_ids` can be passed as an optimization since no search on the database
            is performed and reservation is done on the passed quants set
        """
        self.ensure_one()
        if not lot_id:
            lot_id = self.env['stock.lot']
        if not package_id:
            package_id = self.env['stock.quant.package']
        if not owner_id:
            owner_id = self.env['res.partner']

        quants = self.env['stock.quant']._get_reserve_quantity(
            self.product_id, location_id, need, product_packaging_id=self.product_packaging_id,
            uom_id=self.product_uom, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)

        taken_quantity = 0
        rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        if self.product_id.tracking == 'serial':
            if float_compare(taken_quantity, int(taken_quantity), precision_digits=rounding) != 0:
                taken_quantity = 0
        if self.product_id.tracking == 'lot' and self.picking_id.id and self.product_packaging_id.id and self.product_packaging_id.qty > 0 and self.picking_id.picking_type_id.id and self.picking_id.picking_type_id.packaging_wise_split:
            if float_compare(taken_quantity, int(taken_quantity), precision_digits=rounding) != 0:
                taken_quantity = 0
        # Find a candidate move line to update or create a new one.
        candidate_lines = {}
        for line in self.move_line_ids:
            if line.result_package_id or line.product_id.tracking == 'serial':
                continue
            candidate_lines[line.location_id, line.lot_id, line.package_id, line.owner_id] = line
        move_line_vals = []
        grouped_quants = {}
        # Handle quants duplication
        for quant, quantity in quants:
            if (quant.location_id, quant.lot_id, quant.package_id, quant.owner_id) not in grouped_quants:
                grouped_quants[quant.location_id, quant.lot_id, quant.package_id, quant.owner_id] = [quant, quantity]
            else:
                grouped_quants[quant.location_id, quant.lot_id, quant.package_id, quant.owner_id][1] += quantity
        for reserved_quant, quantity in grouped_quants.values():
            taken_quantity += quantity
            to_update = candidate_lines.get((reserved_quant.location_id, reserved_quant.lot_id, reserved_quant.package_id, reserved_quant.owner_id))
            if to_update:
                uom_quantity = self.product_id.uom_id._compute_quantity(quantity, to_update.product_uom_id, rounding_method='HALF-UP')
                uom_quantity = float_round(uom_quantity, precision_digits=rounding)
                uom_quantity_back_to_product_uom = to_update.product_uom_id._compute_quantity(uom_quantity, self.product_id.uom_id, rounding_method='HALF-UP')
            if to_update and float_compare(quantity, uom_quantity_back_to_product_uom, precision_digits=rounding) == 0:
                to_update.with_context(reserved_quant=reserved_quant).quantity += uom_quantity
            else:
                if self.product_id.tracking == 'serial':
                    # Move lines with serial tracked product_id cannot be to-update candidates. Delay the creation to speed up candidates search + create.
                    move_line_vals.extend(
                        [self._prepare_move_line_vals(quantity=1, reserved_quant=reserved_quant) for i in
                         range(int(quantity))])
                # TODO: CHANGES
                elif self.product_id.tracking == 'lot' and self.picking_id.id and self.product_packaging_id.id and self.product_packaging_id.qty > 0 and self.picking_id.picking_type_id.id and self.picking_id.picking_type_id.packaging_wise_split:

                    packaging_uom = self.product_packaging_id.product_uom_id
                    packaging_uom_qty = self.product_uom._compute_quantity(need,
                                                                           packaging_uom)
                    # if available_quantity < packaging_uom_qty:
                    #     packaging_uom_qty = available_quantity

                    product_packaging_qty = float_round(packaging_uom_qty / self.product_packaging_id.qty,precision_rounding=packaging_uom.rounding)
                    print("product_packaging_qty", product_packaging_qty)

                    list_values = []
                    quantity = packaging_uom_qty

                    # TODO: In v15 we don't need to add 1 because  float_round does this function.
                    if int(product_packaging_qty) < product_packaging_qty and int(
                            product_packaging_qty) + 1 != product_packaging_qty:
                        new_value = int(product_packaging_qty) + 1
                    else:
                        new_value = int(product_packaging_qty)
                    print("new_value", new_value)

                    for count in range(0, new_value):
                        if quantity > self.product_packaging_id.qty:
                            list_values.append(self.product_packaging_id.qty)
                            quantity -= self.product_packaging_id.qty
                        else:
                            list_values.append(quantity)
                            quantity -= quantity

                    print(list_values)
                    if len(list_values) > 0:
                        # Move lines with serial tracked product_id cannot be to-update candidates. Delay the creation to speed up candidates search + create.
                        move_line_vals.extend(
                            [self._prepare_move_line_vals(quantity=i, reserved_quant=reserved_quant) for i in
                             list_values])
                else:
                    self.env['stock.move.line'].create(
                        self._prepare_move_line_vals(quantity=quantity, reserved_quant=reserved_quant))
        self.env['stock.move.line'].create(move_line_vals)
        return taken_quantity