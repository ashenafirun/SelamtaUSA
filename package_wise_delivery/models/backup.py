from odoo import _, api, fields, models
from odoo.tools import float_compare, float_is_zero, float_repr, float_round, float_split, float_split_str
from odoo.exceptions import UserError

class StockPickingExtended(models.Model):
    _inherit = "stock.picking"


    # def action_assign(self):
    #    result = super(StockPickingExtended,self).action_assign()
    #
    #    if self.picking_id.id and self.product_packaging_id.qty > 0 and self.picking_id.picking_type_id.id and self.picking_id.picking_type_id.packaging_wise_split:
    #        packaging_uom = self.product_packaging_id.product_uom_id
    #        packaging_uom_qty = self.product_uom._compute_quantity(self.product_uom_qty,
    #                                                               packaging_uom)
    #        product_packaging_qty = float_round(packaging_uom_qty / self.product_packaging_id.qty,
    #                                            precision_rounding=packaging_uom.rounding)
    #        print("product_packaging_qty", product_packaging_qty)
    #
    #        list_values = []
    #        quantity = self.product_uom_qty
    #
    #        # TODO: In v15 we don't need to add 1 because  float_round does this function.
    #        if int(product_packaging_qty) < product_packaging_qty and int(
    #                product_packaging_qty) + 1 != product_packaging_qty:
    #            new_value = int(product_packaging_qty) + 1
    #        else:
    #            new_value = int(product_packaging_qty)
    #        print("new_value", new_value)
    #
    #        for count in range(0, new_value):
    #            if quantity > self.product_packaging_id.qty:
    #                list_values.append(self.product_packaging_id.qty)
    #                quantity -= self.product_packaging_id.qty
    #            else:
    #                list_values.append(quantity)
    #                quantity -= quantity
    #
    #        package_move_lines = self.move_line_ids.filtered(
    #            lambda r: r.move_id.product_packaging_id.id and r.product_id.tracking == 'lot')
    #
    #        print(list_values)
    #        if len(list_values) > 0:
    #            if package_move_lines.ids:
    #                for line in range(0, len(package_move_lines)):
    #                    package_move_lines[line].product_uom_qty = list_values[line]
    #
    #                for val in list_values[len(package_move_lines)::]:
    #                    copied_vals = package_move_lines[0].copy_data()[0]
    #                    copied_vals['move_id'] = package_move_lines[0].move_id.id
    #                    copied_vals['picking_id'] = package_move_lines[0].picking_id.id
    #                    copied_vals['product_uom_qty'] = val
    #                    new_line = package_move_lines[0].move_id.env['stock.move.line'].create(copied_vals)
    #    return result


class StockPickingTypeExtended(models.Model):
    _inherit = "stock.picking.type"

    packaging_wise_split = fields.Boolean()

class StockMoveLineExtended(models.Model):
    _inherit = "stock.move.line"
    package_line = fields.Boolean()

class StockMoveExtended(models.Model):
    _inherit = "stock.move"

    # def _update_reserved_quantity(self, need, available_quantity, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
    #     """ Create or update move lines.
    #     """
    #     self.ensure_one()
    #
    #     if not lot_id:
    #         lot_id = self.env['stock.production.lot']
    #     if not package_id:
    #         package_id = self.env['stock.quant.package']
    #     if not owner_id:
    #         owner_id = self.env['res.partner']
    #
    #     # do full packaging reservation when it's needed
    #     if self.product_packaging_id and self.product_id.product_tmpl_id.categ_id.packaging_reserve_method == "full":
    #         available_quantity = self.product_packaging_id._check_qty(available_quantity, self.product_id.uom_id, "DOWN")
    #
    #     taken_quantity = min(available_quantity, need)
    #
    #     # `taken_quantity` is in the quants unit of measure. There's a possibility that the move's
    #     # unit of measure won't be respected if we blindly reserve this quantity, a common usecase
    #     # is if the move's unit of measure's rounding does not allow fractional reservation. We chose
    #     # to convert `taken_quantity` to the move's unit of measure with a down rounding method and
    #     # then get it back in the quants unit of measure with an half-up rounding_method. This
    #     # way, we'll never reserve more than allowed. We do not apply this logic if
    #     # `available_quantity` is brought by a chained move line. In this case, `_prepare_move_line_vals`
    #     # will take care of changing the UOM to the UOM of the product.
    #     if not strict and self.product_id.uom_id != self.product_uom:
    #         taken_quantity_move_uom = self.product_id.uom_id._compute_quantity(taken_quantity, self.product_uom, rounding_method='DOWN')
    #         taken_quantity = self.product_uom._compute_quantity(taken_quantity_move_uom, self.product_id.uom_id, rounding_method='HALF-UP')
    #
    #     quants = []
    #     rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
    #
    #     if self.product_id.tracking == 'serial':
    #         if float_compare(taken_quantity, int(taken_quantity), precision_digits=rounding) != 0:
    #             taken_quantity = 0
    #
    #     self.env['base'].flush()
    #     try:
    #         with self.env.cr.savepoint():
    #             if not float_is_zero(taken_quantity, precision_rounding=self.product_id.uom_id.rounding):
    #                 quants = self.env['stock.quant']._update_reserved_quantity(
    #                     self.product_id, location_id, taken_quantity, lot_id=lot_id,
    #                     package_id=package_id, owner_id=owner_id, strict=strict
    #                 )
    #     except UserError:
    #         taken_quantity = 0
    #
    #     # Find a candidate move line to update or create a new one.
    #     serial_move_line_vals = []
    #     for reserved_quant, quantity in quants:
    #         to_update = next((line for line in self.move_line_ids if line._reservation_is_updatable(quantity, reserved_quant)), False)
    #         if to_update:
    #             uom_quantity = self.product_id.uom_id._compute_quantity(quantity, to_update.product_uom_id, rounding_method='HALF-UP')
    #             uom_quantity = float_round(uom_quantity, precision_digits=rounding)
    #             uom_quantity_back_to_product_uom = to_update.product_uom_id._compute_quantity(uom_quantity, self.product_id.uom_id, rounding_method='HALF-UP')
    #         if to_update and float_compare(quantity, uom_quantity_back_to_product_uom, precision_digits=rounding) == 0:
    #             to_update.with_context(bypass_reservation_update=True).product_uom_qty += uom_quantity
    #         else:
    #             if self.product_id.tracking == 'serial':
    #                 # Move lines with serial tracked product_id cannot be to-update candidates. Delay the creation to speed up candidates search + create.
    #                 serial_move_line_vals.extend([self._prepare_move_line_vals(quantity=1, reserved_quant=reserved_quant) for i in range(int(quantity))])
    #             #TODO: CHANGES
    #             elif self.product_id.tracking == 'lot' and self.picking_id.id and self.product_packaging_id.qty > 0 and self.picking_id.picking_type_id.id and self.picking_id.picking_type_id.packaging_wise_split:
    #
    #                 packaging_uom = self.product_packaging_id.product_uom_id
    #                 packaging_uom_qty = self.product_uom._compute_quantity(self.product_uom_qty,
    #                                                                        packaging_uom)
    #                 product_packaging_qty = float_round(packaging_uom_qty / self.product_packaging_id.qty,
    #                                                     precision_rounding=packaging_uom.rounding)
    #                 print("product_packaging_qty", product_packaging_qty)
    #
    #                 list_values = []
    #                 quantity = self.product_uom_qty
    #
    #                 # TODO: In v15 we don't need to add 1 because  float_round does this function.
    #                 if int(product_packaging_qty) < product_packaging_qty and int(
    #                         product_packaging_qty) + 1 != product_packaging_qty:
    #                     new_value = int(product_packaging_qty) + 1
    #                 else:
    #                     new_value = int(product_packaging_qty)
    #                 print("new_value", new_value)
    #
    #                 for count in range(0, new_value):
    #                     if quantity > self.product_packaging_id.qty:
    #                         list_values.append(self.product_packaging_id.qty)
    #                         quantity -= self.product_packaging_id.qty
    #                     else:
    #                         list_values.append(quantity)
    #                         quantity -= quantity
    #
    #                 # package_move_lines = self.move_line_ids.filtered(
    #                 #     lambda r: r.move_id.product_packaging_id.id and r.product_id.tracking == 'lot')
    #
    #                 print(list_values)
    #                 if len(list_values) > 0:
    #             # Move lines with serial tracked product_id cannot be to-update candidates. Delay the creation to speed up candidates search + create.
    #                     serial_move_line_vals.extend([self._prepare_move_line_vals(quantity=list_values[i], reserved_quant=reserved_quant) for i in range(int(available_quantity))])
    #             else:
    #                 self.env['stock.move.line'].create(self._prepare_move_line_vals(quantity=quantity, reserved_quant=reserved_quant))
    #     self.env['stock.move.line'].create(serial_move_line_vals)
    #     return taken_quantity



    def _update_reserved_quantity(self, need, available_quantity, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
        res = super()._update_reserved_quantity(need, available_quantity, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)
        if self.picking_id.id and self.move_line_ids.ids and self.product_packaging_id.qty > 0 and self.picking_id.picking_type_id.id and self.picking_id.picking_type_id.packaging_wise_split:

            package_move_lines = self.move_line_ids.filtered(
                lambda r: r.move_id.product_packaging_id.id and r.product_id.tracking == 'lot')

            package_qty = 0.0
            for package in package_move_lines.filtered(lambda p: p.package_line == True):
                if package.product_uom_qty > self.product_packaging_id.qty:
                    package.product_uom_qty  = self.product_packaging_id.qty
                package_qty +=package.product_uom_qty

            packaging_uom = self.product_packaging_id.product_uom_id
            packaging_uom_qty = self.product_uom._compute_quantity(self.product_uom_qty,
                                                                   packaging_uom)
            packaging_uom_qty -= package_qty

            if available_quantity < packaging_uom_qty:
                packaging_uom_qty = available_quantity

            product_packaging_qty = float_round(packaging_uom_qty / self.product_packaging_id.qty,
                                                precision_rounding=packaging_uom.rounding)
            print("product_packaging_qty", product_packaging_qty)

            list_values = []
            quantity = packaging_uom_qty

            # TODO: In v15 we don't need to add 1 because  float_round does this function.
            if int(product_packaging_qty) < product_packaging_qty and int(product_packaging_qty) + 1 != product_packaging_qty:
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
                if package_move_lines.ids:

                        for val in list_values:
                            copied_vals = package_move_lines[0].copy_data()[0]
                            copied_vals['move_id'] = package_move_lines[0].move_id.id
                            copied_vals['picking_id'] = package_move_lines[0].picking_id.id
                            copied_vals['product_uom_qty'] = val
                            copied_vals['package_line'] = True

                            new_line = package_move_lines[0].move_id.env['stock.move.line'].create(copied_vals)

            for move_line in self.move_line_ids.filtered(lambda r:r.package_line == False or r.state == 'cancel'):
                move_line.sudo().write({'state': 'draft'})
                move_line.unlink()
        return res




            #
            # for move_line in self.move_line_ids.filtered(
            #         lambda r: self.product_packaging_id.id and r.product_id.tracking == 'lot' and r.product_packaging_qty > 0):
            #     if int(move_line.product_packaging_qty) < move_line.product_packaging_qty:
            #         new_value = int(move_line.product_packaging_qty) + 1
            #     else:
            #         new_value = int(move_line.product_packaging_qty)
            #
            #     list_values = []
            #     quantity = move_line.quantity
            #     for count in range(0, new_value):
            #         if quantity > self.product_packaging_id.qty:
            #             list_values.append(self.product_packaging_id.qty)
            #             quantity -= self.product_packaging_id.qty
            #         else:
            #             list_values.append(quantity)
            #             quantity -= quantity
            #
            #     print(list_values)
            #     if list_values:
            #         move_line.quantity = list_values[0]
            #         for val in list_values[1::]:
            #             copied_vals = move_line.copy_data()[0]
            #             copied_vals['move_id'] = self.id
            #             copied_vals['picking_id'] = move_line.picking_id.id
            #             copied_vals['quantity'] = val
            #             new_line = self.env['stock.move.line'].create(copied_vals)

        # return res
#     def _action_assign(self):
#         result = super(StockMoveExtended, self)._action_assign()
#         if self.picking_id.id and self.product_packaging_id.qty > 0 and self.picking_id.picking_type_id.id and self.picking_id.picking_type_id.packaging_wise_split:
#             packaging_uom = self.product_packaging_id.product_uom_id
#             packaging_uom_qty = self.product_uom._compute_quantity(self.product_uom_qty,
#                                                                    packaging_uom)
#             product_packaging_qty = float_round(packaging_uom_qty / self.product_packaging_id.qty,
#                                                 precision_rounding=packaging_uom.rounding)
#             print("product_packaging_qty", product_packaging_qty)
#
#             if self.move_line_ids.ids:
#                 list_values = []
#                 quantity = self.product_uom_qty
#
#                 # TODO: In v15 we don't need to add 1 because  float_round does this function.
#                 if int(product_packaging_qty) < product_packaging_qty and int(product_packaging_qty) + 1 != product_packaging_qty:
#                     new_value = int(product_packaging_qty) + 1
#                 else:
#                     new_value = int(product_packaging_qty)
#                 print("new_value", new_value)
#
#                 for count in range(0, new_value):
#                     if quantity > self.product_packaging_id.qty:
#                         list_values.append(self.product_packaging_id.qty)
#                         quantity -= self.product_packaging_id.qty
#                     else:
#                         list_values.append(quantity)
#                         quantity -= quantity
#
#                 package_move_lines = self.move_line_ids.filtered(
#                     lambda r: r.move_id.product_packaging_id.id and r.product_id.tracking == 'lot')
#
#                 print(list_values)
#                 if len(list_values) > 0:
#                     if package_move_lines.ids:
#
#                         for val in list_values:
#                             copied_vals = package_move_lines[0].copy_data()[0]
#                             copied_vals['move_id'] = package_move_lines[0].move_id.id
#                             copied_vals['picking_id'] = package_move_lines[0].picking_id.id
#                             copied_vals['product_uom_qty'] = val
#                             new_line = package_move_lines[0].move_id.env['stock.move.line'].create(copied_vals)
#
#                         for line in package_move_lines:
#                         #     for line in range(0,len(package_move_lines)):
#                             # package_move_lines[line].product_uom_qty = list_values[line]
#                                 line.unlink()
#                         # self.picking_id.state = 'confirmed'
#                         # self.picking_id.action_cancel()
#                         # self.picking_id.btn_reset_to_draft()
#                         # self.picking_id.action_confirm()
#                         # self.picking_id.action_assign()
#
#         return result

# class StockMoveLineExtended(models.Model):
#     _inherit = "stock.move.line"
#
#     # def _update_reserved_quantity(self, need, available_quantity, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
#         # result =  super()._update_reserved_quantity(need, available_quantity, location_id, lot_id=None, package_id=None, owner_id=None, strict=True)
#     @api.model
#     def create(self,vals):
#         result = super(StockMoveLineExtended,self).create(vals)
#         if result.move_id.id:
#             # for move in result.move_id:
#
#                 packaging_uom = result.move_id.product_packaging_id.product_uom_id
#                 packaging_uom_qty = result.move_id.product_uom._compute_quantity(result.move_id.product_uom_qty,
#                                                                        packaging_uom)
#                 product_packaging_qty = float_round(packaging_uom_qty / result.move_id.product_packaging_id.qty,
#                                                     precision_rounding=packaging_uom.rounding)
#                 print("product_packaging_qty", product_packaging_qty)
#
#                 if result.move_id.move_line_ids.ids and product_packaging_qty > 0:
#                     list_values = []
#                     quantity = result.move_id.product_uom_qty
#
#                     # TODO: In v15 we don't need to add 1 because  float_round does this function.
#                     if int(product_packaging_qty) < product_packaging_qty and int(
#                             product_packaging_qty) + 1 != product_packaging_qty:
#                         new_value = int(product_packaging_qty) + 1
#                     else:
#                         new_value = int(product_packaging_qty)
#                     print("new_value", new_value)
#
#                     for count in range(0, new_value):
#                         if quantity > result.move_id.product_packaging_id.qty:
#                             list_values.append(result.move_id.product_packaging_id.qty)
#                             quantity -= result.move_id.product_packaging_id.qty
#                         else:
#                             list_values.append(quantity)
#                             quantity -= quantity
#
#                     package_move_lines = result.move_id.move_line_ids.filtered(
#                         lambda r: r.move_id.product_packaging_id.id and r.product_id.tracking == 'lot')
#
#                     print(list_values)
#                     if len(list_values) > 0:
#                         if package_move_lines.ids:
#                             for line in range(0,len(package_move_lines)-1):
#                                 package_move_lines[line].product_uom_qty = list_values[line]
#                                 # list_values.pop(0)
#
#                         for val in list_values[len(package_move_lines)::]:
#                             copied_vals = package_move_lines[0].copy_data()[0]
#                             copied_vals['move_id'] = package_move_lines[0].move_id.id
#                             copied_vals['picking_id'] = package_move_lines[0].picking_id.id
#                             copied_vals['product_uom_qty'] = val
#                             new_line = package_move_lines[0].move_id.env['stock.move.line'].create(copied_vals)
#         return result




# class StockMoveExtended(models.Model):
#     _inherit = "stock.move"
#
#     def _action_assign(self):
#         result = super(StockMoveExtended,self)._action_assign()
#     # def _update_reserved_quantity(self, need, available_quantity, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
#     #     result =  super()._update_reserved_quantity(need, available_quantity, location_id, lot_id=None, package_id=None, owner_id=None, strict=True)
#
#         if self.move_line_ids.ids:
#             packaging_uom = self.product_packaging_id.product_uom_id
#             packaging_uom_qty = self.product_uom._compute_quantity(self.product_uom_qty, packaging_uom)
#             product_packaging_qty = float_round(packaging_uom_qty / self.product_packaging_id.qty,
#                                                      precision_rounding=packaging_uom.rounding)
#
#             for move_line in self.move_line_ids.filtered(
#                     lambda r: self.product_packaging_id.id and r.product_id.tracking == 'lot' and r.self.product_packaging_id > 0):
#                            #TODO: In v15 we don't need to add 1 because  float_round does this function.
#                            # if int(product_packaging_qty) < product_packaging_qty:
#                            #     new_value = int(product_packaging_qty) + 1
#                            # else:
#                            #     new_value = int(product_packaging_qty)
#
#                            list_values = []
#                            quantity = move_line.quantity
#                            for count in range(0, product_packaging_qty):
#                                if quantity > self.product_packaging_id.qty:
#                                    list_values.append(self.product_packaging_id.qty)
#                                    quantity -= self.product_packaging_id.qty
#                                else:
#                                    list_values.append(quantity)
#                                    quantity -= quantity
#
#                            print(list_values)
#                            if list_values:
#                                move_line.quantity =list_values[0]
#                                for val in list_values[1::]:
#                                    copied_vals = move_line.copy_data()[0]
#                                    copied_vals['move_id'] = self.id
#                                    copied_vals['picking_id'] = move_line.picking_id.id
#                                    copied_vals['quantity'] = val
#                                    new_line = self.env['stock.move.line'].create(copied_vals)
#         return result
#
#
#
#
#





# class StockPickingExtended(models.Model):
#     _inherit = "stock.picking"
#
#     def action_assign(self):
#        result = super(StockPickingExtended,self).action_assign()
#        if self.move_lines.ids:
#            for move in self.move_lines:
#
#                packaging_uom = move.product_packaging_id.product_uom_id
#                packaging_uom_qty = move.product_uom._compute_quantity(move.product_uom_qty,
#                                                                                    packaging_uom)
#                product_packaging_qty = float_round(packaging_uom_qty / move.product_packaging_id.qty,
#                                                    precision_rounding=packaging_uom.rounding)
#                print("product_packaging_qty", product_packaging_qty)
#
#                if move.move_line_ids.ids and product_packaging_qty > 0:
#                    list_values = []
#                    quantity = move.product_uom_qty
#
#                    # TODO: In v15 we don't need to add 1 because  float_round does this function.
#                    if int(product_packaging_qty) < product_packaging_qty and int(product_packaging_qty) + 1 != product_packaging_qty:
#                        new_value = int(product_packaging_qty) + 1
#                    else:
#                        new_value = int(product_packaging_qty)
#                    print("new_value", new_value)
#
#                    for count in range(0, new_value):
#                        if quantity > move.product_packaging_id.qty:
#                            list_values.append(move.product_packaging_id.qty)
#                            quantity -= move.product_packaging_id.qty
#                        else:
#                            list_values.append(quantity)
#                            quantity -= quantity
#
#                    package_move_lines = move.move_line_ids.filtered(lambda r: r.move_id.product_packaging_id.id and r.product_id.tracking == 'lot')
#
#                    print(list_values)
#                    if list_values:
#                        if package_move_lines.ids:
#                            for line in package_move_lines:
#                                line.product_uom_qty = list_values[0]
#                                list_values.pop(0)
#
#                        for val in list_values:
#                            copied_vals = package_move_lines[0].copy_data()[0]
#                            copied_vals['move_id'] = package_move_lines[0].move_id.id
#                            copied_vals['picking_id'] = package_move_lines[0].picking_id.id
#                            copied_vals['product_uom_qty'] = val
#                            new_line = package_move_lines[0].move_id.env['stock.move.line'].create(copied_vals)
#
#        return result
