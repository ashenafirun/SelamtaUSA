import math
from odoo import models, _
from odoo.tools.float_utils import float_compare, float_round
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def write(self, vals):
        res = super().write(vals)
        if vals.get('state') == 'assigned':
            if not self.env.context.get('split_packaging_running'):
                self.with_context(
                    split_packaging_running=True
                )._split_move_lines_by_packaging()
        return res

    def action_assign(self):
        res = super().action_assign()
        if not self.env.context.get('split_packaging_running'):
            self.with_context(
                split_packaging_running=True
            )._split_move_lines_by_packaging()
        return res

    def _split_move_lines_by_packaging(self):
        """
        Split move LINES (not moves) by packaging.
        The move stays as one line on the Operations tab showing the full demand.
        Inside each move, the move lines are split by pkg_qty.
        Workers see total on delivery, details when they open the move.
        """
        for picking in self:
            if picking.state in ('done', 'cancel'):
                continue

            for move in picking.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
            ):
                product = move.product_id
                packaging = (
                    product.packaging_ids[:1]
                    or product.product_tmpl_id.packaging_ids[:1]
                )

                if not packaging or not packaging.qty or packaging.qty <= 0:
                    continue

                pkg_qty = packaging.qty
                uom_rounding = move.product_uom.rounding

                # Work on move lines that are not yet split
                for line in move.move_line_ids:
                    line_qty = line.quantity  # reserved qty in Odoo 18

                    if float_compare(
                        line_qty, pkg_qty, precision_rounding=uom_rounding
                    ) <= 0:
                        # Already pkg_qty or less — nothing to split
                        continue

                    num_full = math.floor(
                        float_round(line_qty / pkg_qty, precision_digits=6)
                    )
                    remainder = float_round(
                        line_qty - (num_full * pkg_qty),
                        precision_rounding=uom_rounding
                    )
                    has_remainder = float_compare(
                        remainder, 0, precision_rounding=uom_rounding
                    ) > 0
                    total_pkgs = num_full + (1 if has_remainder else 0)

                    if total_pkgs <= 1:
                        continue

                    _logger.info(
                        "SPLIT-PKG: move_line for %s qty=%s → %s lines of %s",
                        product.name, line_qty, total_pkgs, pkg_qty
                    )

                    # Reduce the original line to pkg_qty
                    line.with_context(
                        split_packaging_running=True
                    ).write({
                        'quantity': pkg_qty,
                        'qty_done': 0,
                        'result_package_id': False,
                    })

                    # Create new move lines for remaining packages
                    for i in range(1, total_pkgs):
                        qty = pkg_qty if i < num_full else remainder
                        if float_compare(
                            qty, 0, precision_rounding=uom_rounding
                        ) <= 0:
                            continue
                        self.env['stock.move.line'].with_context(
                            split_packaging_running=True
                        ).create({
                            'move_id': move.id,
                            'picking_id': picking.id,
                            'product_id': product.id,
                            'product_uom_id': line.product_uom_id.id,
                            'location_id': line.location_id.id,
                            'location_dest_id': line.location_dest_id.id,
                            'lot_id': line.lot_id.id if line.lot_id else False,
                            'owner_id': line.owner_id.id if line.owner_id else False,
                            'package_id': line.package_id.id if line.package_id else False,
                            'quantity': qty,
                            'qty_done': 0,
                            'result_package_id': False,
                        })

                    _logger.info(
                        "SPLIT-PKG: done splitting move_line for %s", product.name
                    )
