# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api
from datetime import datetime, timedelta

OPERATOR_CONDITION = {"==": "=", "<=": ">=", "<": ">", ">=": "<=", ">": "<"}


class CreditCode(models.Model):
    _name = "credit.code"
    _description = "Credit Code"

    def calculate_onorder_amount(
        self, partner, operator_condition, days, sale_order, partner_currency_id
    ):
        past_due_amt = 0.0
        cr = self.env.cr
        delivery_date = datetime.now().date()
        check_date = delivery_date - timedelta(days=days)
        operator_condition = OPERATOR_CONDITION[operator_condition]
        user_company = self.env.user.company_id.id
        # calculate partner credit amount.
        dates_query = "(l.date_maturity "
        dates_query += operator_condition
        dates_query += " %s)"
        query = (
            """SELECT l.id
                FROM account_move_line AS l,
                account_account, account_move am
                WHERE (l.account_id = account_account.id) AND (l.move_id = am.id)
                    AND (am.state IN ('draft', 'posted'))
                    AND (account_account.account_type = 'asset_receivable')
                    AND (l.partner_id = %s)
                    AND l.company_id = %s
                    AND """
            + dates_query
            + """
                    """
        )
        cr.execute(query, [partner, user_company, check_date])
        aml_ids = cr.fetchall()
        aml_ids = aml_ids and [x[0] for x in aml_ids] or []
        for line in self.env["account.move.line"].browse(aml_ids):
            open_amount = line.balance
            if line.currency_id and line.currency_id.id != partner_currency_id.id:
                open_amount = line.currency_id.compute(open_amount, partner_currency_id)
            past_due_amt += open_amount

        partner_id = self.env['res.partner'].browse(partner)

        order_amount = sum(partner_id.sale_order_ids.filtered(
            lambda order: order.state in ['sale', 'approved'] and not order.invoice_ids
            ).mapped('amount_total'))
        return past_due_amt + order_amount

    def check_approval_status(self, sale_order=None, move=None):
        """
        Return True if the partner's credit limit covers the sum of all open
        receivables plus the current order/invoice amount.

        Uses the accounting partner (commercial partner) to ensure consistency
        with how Odoo resolves invoicing partners.
        """
        record = sale_order or move or False

        accounting_partner = self.env["res.partner"]._find_accounting_partner(
            record.partner_id
        )
        open_receivable_amt = self.calculate_onorder_amount(
            accounting_partner.id, ">=", 0, record, accounting_partner.currency_id
        )
        total_exposure = open_receivable_amt + record.amount_total
        return accounting_partner.credit_limit >= total_exposure, False


class OrderlineApprovalHistory(models.Model):
    _name = "orderline.approval.history"
    _description = "Orderline Approval History"
    _rec_name = "display_name"

    # _sql_constraints = [
    #     (
    #         "one_parent_only",
    #         "CHECK((order_id IS NULL) != (invoice_id IS NULL))",
    #         "An approval history record must be linked to either a Sale Order or an Invoice, not both or neither.",
    #     )
    # ]

    display_name = fields.Char(
        string="Description",
        compute="_compute_display_name",
    )

    user_id = fields.Many2one(
        "res.users",
        string="User",
        default=lambda self: self.env.user,
        help="User who performed the approval action.",
    )
    date = fields.Date(
        string="Date",
        default=fields.Date.today,
        help="Date of the approval action.",
    )
    approved_amount = fields.Float(
        string="Approval Amount",
        help="Amount approved for this order or invoice.",
    )
    reason = fields.Text(
        string="Reason",
        help="Reason for approval or rejection.",
    )
    order_id = fields.Many2one(
        "sale.order",
        string="Sale Order",
        ondelete="cascade",
    )
    invoice_id = fields.Many2one(
        "account.move",
        string="Invoice",
        ondelete="cascade",
    )
    status = fields.Selection(
        [("draft", "-"), ("approved", "Approved"), ("rejected", "Rejected")],
        string="Status",
        default="draft",
        copy=False,
        help="Status of the approval action.",
    )

    @api.depends("date", "status", "user_id")
    def _compute_display_name(self):
        status_labels = dict(self._fields["status"].selection)
        for rec in self:
            rec.display_name = "%s — %s (%s)" % (
                rec.date or "",
                status_labels.get(rec.status, ""),
                rec.user_id.name or "",
            )
