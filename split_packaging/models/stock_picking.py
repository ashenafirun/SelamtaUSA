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
            packagings = (
                product.packaging_ids
                or product.product_tmpl_id.packaging_ids
            ).filtered(lambda p: p.qty and p.qty > 0)

            if not packagings:
                continue

            # Try every packaging size on this product, largest first, so a
            # line gets split using whichever sizes actually divide it.
            # This fixes the old behavior of only ever using packaging_ids[:1],
            # which broke scanning whenever an order used more than one
            # packaging for the same product.
            pkg_sizes = sorted(set(packagings.mapped('qty')), reverse=True)
            uom_rounding = move.product_uom.rounding

            reserved_lines = move.move_line_ids.filtered(
                lambda l: float_compare(
                    l.quantity, 0, precision_rounding=uom_rounding
                ) > 0 and l.qty_done == 0
            )

            if not reserved_lines:
                continue

            # Skip lines that are already sized to one of the known
            # packaging quantities - nothing further to split.
            if all(
                any(
                    float_compare(l.quantity, sz, precision_rounding=uom_rounding) == 0
                    for sz in pkg_sizes
                )
                for l in reserved_lines
            ) and len(reserved_lines) > 1:
                continue

            for line in reserved_lines:
                line_qty = line.quantity
                if any(
                    float_compare(line_qty, sz, precision_rounding=uom_rounding) == 0
                    for sz in pkg_sizes
                ):
                    continue
                if float_compare(line_qty, min(pkg_sizes), precision_rounding=uom_rounding) <= 0:
                    continue

                # Greedily break line_qty into chunks using the available
                # packaging sizes (largest first), with any true leftover
                # kept as its own remainder chunk.
                remaining = line_qty
                chunks = []
                for sz in pkg_sizes:
                    if float_compare(remaining, sz, precision_rounding=uom_rounding) <= 0:
                        continue
                    count = math.floor(float_round(remaining / sz, precision_digits=6))
                    if count <= 0:
                        continue
                    chunks.extend([sz] * count)
                    remaining = float_round(
                        remaining - (count * sz), precision_rounding=uom_rounding
                    )

                if float_compare(remaining, 0, precision_rounding=uom_rounding) > 0:
                    chunks.append(remaining)

                if len(chunks) <= 1:
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

                line.sudo().write({'quantity': chunks[0]})

                for qty in chunks[1:]:
                    if float_compare(qty, 0, precision_rounding=uom_rounding) <= 0:
                        continue
                    new_line = MoveLine.sudo().create(dict(base_line_vals))
                    new_line.sudo().write({'quantity': qty})

                _logger.info(
                    "SPLIT-PKG: %s → %s lines (sizes used: %s)",
                    product.name, len(chunks), pkg_sizes
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
                # Find lot-tracked move lines and set their 'picked' flag.
                # Odoo 17+ has a dedicated 'picked' boolean field on
                # stock.move.line specifically so a line can be marked as
                # picked WITHOUT setting qty_done - that keeps the reserved
                # quantity available for the Barcode app to bind to a
                # subsequently-scanned package/box. Previously this wrote
                # qty_done = quantity instead, which marked the line as
                # fully finished and left nothing "available" for the app
                # to assign a new box scan to.
                lot_lines = picking.move_line_ids.filtered(
                    lambda l: l.product_id.tracking in ('lot', 'serial')
                    and l.state not in ('done', 'cancel')
                )
                for line in lot_lines:
                    line.sudo().write({'picked':
