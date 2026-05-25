import math
from odoo import models, _
from odoo.tools.float_utils import float_compare, float_round
import logging

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_assign(self):
        res = super()._action_assign()
        if not self.env.context.get('split_packaging_running'):
            self.with_context(split_packaging_running=True)._split_by_packaging()
        return res

    def _split_by_packaging(self):
        _logger.info("SPLIT-PKG: _split_by_packaging called on %s moves", len(self))

        for move in self:
            _logger.info(
                "SPLIT-PKG: checking move id=%s product=%s state=%s qty=%s",
                move.id, move.product_id.name, move.state, move.product_uom_qty
            )

            if move.state in ('draft', 'done', 'cancel'):
                _logger.info("SPLIT-PKG: skipping — state is %s", move.state)
                continue

            product = move.product_id
            packaging = (
                product.packaging_ids[:1]
                or product.product_tmpl_id.packaging_ids[:1]
            )

            _logger.info(
                "SPLIT-PKG: product=%s packaging=%s",
                product.name, packaging
            )

            if not packaging or not packaging.qty or packaging.qty <= 0:
                _logger.info("SPLIT-PKG: NO packaging found for %s — skipping", product.name)
                continue

            pkg_qty = packaging.qty
            uom_rounding = move.product_uom.rounding
            total_qty = move.product_uom_qty

            _logger.info(
                "SPLIT-PKG: pkg_qty=%s total_qty=%s uom=%s",
                pkg_qty, total_qty, move.product_uom.name
            )

            if float_compare(total_qty, pkg_qty, precision_rounding=uom_rounding) <= 0:
                _logger.info("SPLIT-PKG: qty <= pkg_qty, nothing to split")
                continue

            num_full = math.floor(float_round(total_qty / pkg_qty, precision_digits=6))
            remainder = float_round(
                total_qty - (num_full * pkg_qty),
                precision_rounding=uom_rounding
            )
            has_remainder = float_compare(remainder, 0, precision_rounding=uom_rounding) > 0
            total_pkgs = num_full + (1 if has_remainder else 0)

            _logger.info(
                "SPLIT-PKG: num_full=%s remainder=%s total_pkgs=%s",
                num_full, remainder, total_pkgs
            )

            if total_pkgs <= 1:
                _logger.info("SPLIT-PKG: only 1 pkg needed, skipping")
                continue

            # Test what _split returns
            _logger.info("SPLIT-PKG: calling _split(%s) on move %s", total_qty - pkg_qty, move.id)
            try:
                test_result = move._split(total_qty - pkg_qty)
                _logger.info(
                    "SPLIT-PKG: _split returned type=%s value=%s",
                    type(test_result), test_result
                )
            except Exception as e:
                _logger.error("SPLIT-PKG: _split() failed: %s", str(e))
                continue

            # Handle both return types
            new_move_ids = []
            if test_result and isinstance(test_result[0], dict):
                _logger.info("SPLIT-PKG: Odoo 18 mode — creating moves from dicts")
                new_move = self.env['stock.move'].with_context(
                    split_packaging_running=True
                ).create(test_result)
                new_move_ids.extend(new_move.ids)
                new_move.with_context(split_packaging_running=True)._action_confirm()
            elif test_result:
                _logger.info("SPLIT-PKG: classic mode — got IDs: %s", test_result)
                new_move_ids.extend(
                    [r if isinstance(r, int) else r.id for r in test_result]
                )

            # Now further split new moves if needed
            if new_move_ids:
                remaining_moves = self.env['stock.move'].browse(new_move_ids)
                # Recursively split further if still > pkg_qty
                remaining_moves.with_context(
                    split_packaging_running=True
                )._split_by_packaging()
                # Assign all
                remaining_moves.with_context(
                    split_packaging_running=True
                )._action_assign()

            _logger.info("SPLIT-PKG: done for %s, new_move_ids=%s", product.name, new_move_ids)
