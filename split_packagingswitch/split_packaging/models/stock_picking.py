import math
from odoo import models, fields, api, _
from odoo.tools.float_utils import float_compare, float_round
import logging

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_assign(self):
        res = super()._action_assign()
        if not self.env.context.get('split_packaging_running'):
            self.with_context(
                split_packaging_running=True
            )._split_reserved_lines_by_packaging()
        return res

    def _split_reserved_lines_by_packaging(self):
        MoveLine = self.env['stock.move.line']

        for move in self:
            if move.state in ('done', 'cancel'):
                continue

            product = move.product_id
            packaging = (
                product.packaging_ids[:1]
                or product.product_tmpl_id.packaging_ids[:1]
            )

            if not packaging or not packaging.qty or packaging.qty <= 0:
                continue

            pkg_qty = packaging.qty
            uom_rounding = move.product_uom.rounding

            reserved_lines = move.move_line_ids.filtered(
                lambda l: float_compare(
                    l.quantity, 0, precision_rounding=uom_rounding
                ) > 0 and l.qty_done == 0
            )

            if not reserved_lines:
                continue

            if all(
                float_compare(l.quantity, pkg_qty, precision_rounding=uom_rounding) <= 0
                for l in reserved_lines
            ) and len(reserved_lines) > 1:
                continue

            for line in reserved_lines:
                line_qty = line.quantity
                if float_compare(line_qty, pkg_qty, precision_rounding=uom_rounding) <= 0:
                    continue

                num_full = math.floor(float_round(line_qty / pkg_qty, precision_digits=6))
                remainder = float_round(
                    line_qty - (num_full * pkg_qty), precision_rounding=uom_rounding
                )
                has_remainder = float_compare(remainder, 0, precision_rounding=uom_rounding) > 0
                total_pkgs = num_full + (1 if has_remainder else 0)

                if total_pkgs <= 1:
                    continue

                base_line_vals = {
                    'move_id': move.id,
                    'picking_id': move.picking_id.id,
                    'product_id': product.id,
                    'product_uom_id': line.product_uom_id.id,
                    'location_id': line.location_id.id,
                    'location_dest_id': line.location_dest_id.id,
                    'lot_id': line.lot_id.id if line.lot_id else False,
                    'owner_id': line.owner_id.id if line.owner_id else False,
                    'package_id': line.package_id.id if line.package_id else False,
                    'qty_done': 0,
                    'result_package_id': False,
                }

                line.sudo().write({'quantity': pkg_qty})

                for i in range(1, total_pkgs):
                    qty = pkg_qty if i < num_full else remainder
                    if float_compare(qty, 0, precision_rounding=uom_rounding) <= 0:
                        continue
                    new_line = MoveLine.sudo().create(dict(base_line_vals))
                    new_line.sudo().write({'quantity': qty})

                _logger.info(
                    "SPLIT-PKG: %s → %s lines", product.name, total_pkgs
                )


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    mark_lot_lines_picked = fields.Boolean(
        string='Mark Lot Products as Picked',
        default=False,
        help='Marks lot-tracked products as Picked so the Barcode app shows the ▼ dropdown.'
    )

    def write(self, vals):
        res = super().write(vals)

        if 'mark_lot_lines_picked' in vals:
            picked_value = vals['mark_lot_lines_picked']
            for picking in self:
                # Find lot-tracked move lines and set qty_done accordingly
                # In Odoo 18, "Picked" checkbox = move_line_ids where qty_done > 0
                # The Picked column on the move level checks if all lines have qty_done set
                # We set qty_done = quantity (reserved qty) to mark as picked
                lot_lines = picking.move_line_ids.filtered(
                    lambda l: l.product_id.tracking in ('lot', 'serial')
                    and l.state not in ('done', 'cancel')
                )
                if picked_value:
                    # Mark as picked: set qty_done = reserved quantity
                    for line in lot_lines:
                        if line.quantity > 0 and line.qty_done == 0:
                            line.sudo().write({'qty_done': line.quantity})
                else:
                    # Unmark: reset qty_done to 0
                    for line in lot_lines:
                        line.sudo().write({'qty_done': 0})

        return res

    def action_toggle_lot_picked(self):
        """Toggle Mark Lot Products Picked on/off."""
        self.ensure_one()
        self.write({'mark_lot_lines_picked': not self.mark_lot_lines_picked})

    def action_mark_lot_lines_picked_barcode(self):
        """Called from barcode app button. Toggles picked state for lot lines."""
        self.ensure_one()
        lot_lines = self.move_line_ids.filtered(
            lambda l: l.product_id.tracking in ('lot', 'serial')
            and l.state not in ('done', 'cancel')
        )
        if not lot_lines:
            return False
        all_picked = all(l.qty_done > 0 for l in lot_lines)
        new_val = not all_picked
        self.write({'mark_lot_lines_picked': new_val})
        return new_val
