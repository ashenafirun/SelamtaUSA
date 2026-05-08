# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = "sale.order"

    approval_history_ids = fields.One2many(
        "orderline.approval.history", "order_id", string="Approval History"
    )
    state = fields.Selection(
        selection_add=[("credit_hold", "CC Hold"), ("approved", "Approved")],
        string="Status",
        copy=False,
        default="draft",
        ondelete={
            "credit_hold": "set default",
            "approved": "set default",
        },
    )
    upgrade_approval = fields.Boolean(
        string="Approval based on Order Limit", copy=False
    )
    approved_amount = fields.Float(string="Approved Amount", copy=False)
    already_delivery_generated = fields.Boolean(
        string="Already Delivery Generated", copy=False
    )
    delivery_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("waiting", "Waiting Another Operation"),
            ("confirmed", "Waiting"),
            ("assigned", "Ready"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        string="Latest Delivery State",
        compute="_compute_latest_delivery_state",
        store=True,
    )

    @api.depends("picking_ids.state", "picking_ids.create_date")
    def _compute_latest_delivery_state(self):
        for order in self:
            # Ensure there's at least one picking record
            if order.picking_ids:
                # Find the picking with the latest `create_date`
                latest_picking = max(
                    order.picking_ids, key=lambda picking: picking.create_date
                )
                order.delivery_state = latest_picking.state
            else:
                # No pickings available, so we set an empty state
                order.delivery_state = False

    def action_draft(self):
        res = super().action_draft()
        self.write(
            {
                "approved_amount": False,
                "upgrade_approval": False,
                "already_delivery_generated": False,
            }
        )
        return res

    def action_confirm(self):
        """Override to intercept orders that exceed the partner credit limit."""
        # Separate orders that pass credit check from those that don't

        credit_hold_orders = self.env["sale.order"]
        normal_orders = self.env["sale.order"]

        for order in self:
            if order.state not in ["draft", "sent"]:
                continue

            if order.partner_id.credit_limit > 0.0 and not order.transaction_ids:
                check_false, cc_hold = self.env["credit.code"].check_approval_status(
                    sale_order=order
                )
                if cc_hold:
                    credit_hold_orders |= order
                    continue
                if (
                    not check_false
                    and order.amount_total > order.partner_id.remaining_credit_limit
                ):
                    credit_hold_orders |= order
                    continue
            normal_orders |= order

        for order in credit_hold_orders:
            if order.partner_id not in order.message_partner_ids:
                order.message_subscribe([order.partner_id.id])
            order.state = "credit_hold"
            order.message_post(
                body=_(
                    "Order placed on Credit Hold: amount exceeds the partner's remaining credit limit."
                )
            )

        # Confirm the rest through the standard Odoo flow
        if normal_orders:
            result = super(SaleOrder, normal_orders).action_confirm()

            # Generate delivery for orders with no credit limit enforced
            for order in normal_orders:
                if not order.already_delivery_generated:
                    order.already_delivery_generated = True
        return True

    def delivery_order(self):
        for order in self:
            order.already_delivery_generated = True
            if order.approved_amount < order.amount_total and order.upgrade_approval:
                raise UserError(
                    _("First reduce order quantity based on your Approved amount : %s")
                    % (order.approved_amount)
                )
            else:
                for sale_order_line in order.order_line:
                    sale_order_line._action_launch_stock_rule()
                order.state = "sale"
        if self.create_uid.has_group("sale.group_auto_done_setting"):
            self.action_lock()
        return True

    def credit_approve(self):
        if not self.env.user.has_group(
            "sales_team.group_sale_manager"
        ) and not self.env.user.has_group("account.group_account_manager"):
            raise UserError(
                _(
                    "Only users with '%(sale_manager)s' or '%(account_manager)s' rights are allowed to give approval!",
                    sale_manager=self.env.ref(
                        "sales_team.group_sale_manager"
                    ).display_name,
                    account_manager=self.env.ref(
                        "account.group_account_manager"
                    ).display_name,
                )
            )

        if self.env.user.id == self.user_id.id:
            raise UserError(_("You cannot approve your own record!"))
        view_id = self.env.ref("payment_credit_limit.view_approval_credit_limit", False)
        return {
            "type": "ir.actions.act_window",
            "name": _("Credit Limit Approval"),
            "view_type": "form",
            "view_mode": "form",
            "res_model": "approval.credit.limit",
            "target": "new",
            "views": [(view_id.id if view_id else False, "form")],
            "view_id": view_id.id if view_id else False,
        }

    def cancel_order_on_cc(self):
        if not self.env.user.has_group(
            "sales_team.group_sale_manager"
        ) and not self.env.user.has_group("account.group_account_manager"):
            raise UserError(
                _(
                    "Only users with '%(sale_manager)s' or '%(account_manager)s' rights are allowed to reject approval requests!",
                    sale_manager=self.env.ref(
                        "sales_team.group_sale_manager"
                    ).display_name,
                    account_manager=self.env.ref(
                        "account.group_account_manager"
                    ).display_name,
                )
            )
        if self.env.user.id == self.user_id.id:
            raise UserError(_("You cannot reject your own record!"))
        view_id = self.env.ref("payment_credit_limit.view_cancel_credit_limit", False)
        return {
            "type": "ir.actions.act_window",
            "name": _("Cancel Approval"),
            "view_type": "form",
            "view_mode": "form",
            "res_model": "approval.credit.limit",
            "target": "new",
            "views": [(view_id.id if view_id else False, "form")],
            "view_id": view_id.id if view_id else False,
        }


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        """
        Launch procurement group run method with required/custom fields genrated by a
        sale order line. procurement group will launch '_run_pull', '_run_buy' or '_run_manufacture'
        depending on the sale order line product rule.
        """
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        procurements = []
        for line in self:
            if line.product_id.type not in ("consu", "product"):
                continue
            qty = 0.0
            for move in line.move_ids.filtered(lambda r: r.state != "cancel"):
                qty += move.product_uom._compute_quantity(
                    move.product_uom_qty, line.product_uom, rounding_method="HALF-UP"
                )
            if (
                float_compare(qty, line.product_uom_qty, precision_digits=precision)
                >= 0
            ):
                continue

            group_id = line.order_id.procurement_group_id
            if not group_id:
                group_id = self.env["procurement.group"].create(
                    {
                        "name": line.order_id.name,
                        "move_type": line.order_id.picking_policy,
                        "sale_id": line.order_id.id,
                        "partner_id": line.order_id.partner_shipping_id.id,
                    }
                )
                line.order_id.procurement_group_id = group_id
            else:
                # In case the procurement group is already created and the order was
                # cancelled, we need to update certain values of the group.
                updated_vals = {}
                if group_id.partner_id != line.order_id.partner_shipping_id:
                    updated_vals.update(
                        {"partner_id": line.order_id.partner_shipping_id.id}
                    )
                if group_id.move_type != line.order_id.picking_policy:
                    updated_vals.update({"move_type": line.order_id.picking_policy})
                if updated_vals:
                    group_id.write(updated_vals)

            values = line._prepare_procurement_values(group_id=group_id)
            product_qty = line.product_uom_qty - qty

            procurement_uom = line.product_uom
            quant_uom = line.product_id.uom_id
            procurements.append(
                self.env["procurement.group"].Procurement(
                    line.product_id,
                    product_qty,
                    procurement_uom,
                    line.order_id.partner_shipping_id.property_stock_customer,
                    line.name,
                    line.order_id.name,
                    line.order_id.company_id,
                    values,
                )
            )

            get_param = self.env["ir.config_parameter"].sudo().get_param
            if (
                procurement_uom.id != quant_uom.id
                and get_param("stock.propagate_uom") != "1"
            ):
                line.product_uom._compute_quantity(
                    product_qty, quant_uom, rounding_method="HALF-UP"
                )

            try:
                self.env["procurement.group"].run(procurements)
            except UserError as procurements:
                procurements.append(procurements.name)
        orders = list(set(x.order_id for x in self))
        for order in orders:
            reassign = order.picking_ids.filtered(
                lambda x: x.state == "confirmed"
                or (x.state in ["waiting", "assigned"] and not x.printed)
            )
            if reassign:
                reassign.do_unreserve()
                reassign.action_assign()
        return True
