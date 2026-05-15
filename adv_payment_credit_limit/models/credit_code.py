# Part of Odoo. See LICENSE file for full copyright and licensing details.

import operator as o
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

OPERATOR_MAP = {"=": o.eq, "==": o.eq, ">=": o.ge, "<=": o.le, "<": o.lt, ">": o.gt}

OPERATOR_CONDITION = {"==": "=", "<=": ">=", "<": ">", ">=": "<=", ">": "<"}


class CreditCode(models.Model):
    _inherit = "credit.code"
    _order = "code"
    _rec_names_search = ["name", "code"]

    code = fields.Integer("Code", required=True, help="Code of credit code rule.")
    name = fields.Char("Name", required=True, help="Name of credit code rule.")
    description = fields.Text("Description", help="Description of credit code rule.")
    credit_check = fields.Selection(
        [
            ("credit_hold", "Credit Hold"),
            ("check_limit", "Check Limit"),
            ("unlimited_account", "Unlimited Account"),
            ("base_on_rule", "Based on Rules"),
        ],
        string="Check Credit",
        default="check_limit",
        required=True,
        help="Credit check type.",
    )
    credit_limit_enforced = fields.Boolean(
        "Credit Limit Enforced?", help="Compulsory check credit limit."
    )
    line_ids = fields.One2many(
        "credit.code.line",
        "credit_code_id",
        "Credit Code Rules",
        help="Check credit code conditions.",
    )
    active = fields.Boolean(default=True)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for credit_code in self:
            code = credit_code.code or ""
            name = credit_code.name or ""
            credit_code.display_name = _("[%(code)s] %(name)s", code=code, name=name)

    @api.constrains("code")
    def _check_code_unique(self):
        for record in self:
            if not record.code:
                continue

            duplicate = self.sudo().search(
                [
                    ("code", "=", record.code),
                    ("id", "!=", record.id),
                ]
            )
            if duplicate:
                raise ValidationError(
                    _(
                        "The code '%s' already exists. The code must be unique.",
                        record.code,
                    )
                )

    def calculate_onorder_amount(
        self, partner, operator_condition, days, sale_order, partner_currency_id
    ):
        past_due_amt = 0.0
        cr = self.env.cr
        # myTime = datetime.strptime(str(sale_order.date_order), DEFAULT_SERVER_DATETIME_FORMAT).date()

        order_date = (
            getattr(sale_order, "date_order", None)
            or getattr(sale_order, "invoice_date", None)
            or getattr(sale_order, "date", None)
            or fields.Date.today()
        )
        # myTime = (
        #     order_date
        #     if not isinstance(order_date, str)
        #     else datetime.strptime(order_date, "%Y-%m-%d").date()
        # )
        if isinstance(order_date, str):
            myTime = datetime.strptime(order_date, "%Y-%m-%d").date()
        else:
            myTime = fields.Date.to_date(order_date)
        check_date = myTime - timedelta(days=days)
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
                    AND (account_account.account_type IN ('asset_receivable'))
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
        # calculate draft account invoices past due amount
        invoices = self.env["account.move"].search(
            [("partner_id", "=", partner), ("state", "=", "draft")]
        )
        if invoices:
            for invoice in invoices:
                if invoice.invoice_payment_term_id:
                    sign = 1 if invoice.is_inbound(include_receipts=True) else -1
                    totlines = invoice.invoice_payment_term_id.with_context(
                        currency_id=invoice.currency_id.id
                    )._compute_terms(
                        # invoice.amount_total,
                        invoice.invoice_date,
                        invoice.currency_id,
                        invoice.company_id,
                        invoice.amount_tax,
                        invoice.amount_untaxed * sign,
                        sign,
                        invoice.amount_untaxed_signed,
                        invoice.amount_untaxed * sign,
                    )
                    if invoice.invoice_date and invoice.amount_total:
                        for total_line in totlines.get('line_ids'):
                            open_amount = total_line.get('foreign_amount')
                            if not invoice.currency_id == partner_currency_id:
                                open_amount = total_line.get('company_amount')
                            date = datetime.strptime(str(total_line.get('date')), "%Y-%m-%d").date()
                            if check_date >= date:
                                if invoice.move_type == "out_invoice":
                                    past_due_amt += open_amount
                                elif invoice.move_type == "out_refund":
                                    past_due_amt -= open_amount

                    # if invoice.invoice_date and invoice.amount_total:
                    #     for total_line in totlines:
                    #         open_amount = total_line[1]
                    #         if not invoice.currency_id == partner_currency_id:
                    #             open_amount = invoice.currency_id.compute(
                    #                 total_line[1], partner_currency_id
                    #             )
                    #         date = datetime.strptime(total_line[0], "%Y-%m-%d").date()
                    #         if check_date >= date:
                    #             if invoice.move_type == "out_invoice":
                    #                 past_due_amt += open_amount
                    #             elif invoice.move_type == "out_refund":
                    #                 past_due_amt -= open_amount
                else:
                    open_amount = invoice.amount_total
                    if not invoice.currency_id == partner_currency_id:
                        open_amount = invoice.currency_id.compute(
                            invoice.amount_total, partner_currency_id
                        )
                    if invoice.move_type == "out_invoice":
                        past_due_amt += open_amount
                    elif invoice.move_type == "out_refund":
                        if past_due_amt >= open_amount:
                            past_due_amt -= open_amount

        partner_id = self.env["res.partner"].browse(partner)
        order_amount = sum(
            partner_id.sale_order_ids.filtered(
                lambda order: order.state in ["sale", "approved"]
                and not order.invoice_ids
            ).mapped("amount_total")
        )
        return past_due_amt + order_amount

    def calculate_based_on(
        self, credit_limit, past_due_amt, rule_of, based_amt, based_opt, value
    ):
        """
        Evaluate whether a credit rule condition is met.

        - rule_of:   'past_due' or 'credit_limit' — the base figure to scale
        - based_amt: 'percentage' or 'amount' — how `value` is interpreted
        - based_opt: comparison operator string e.g. '>=', '<'
        - value:     threshold value (percentage 0–100, or absolute amount)

        Returns True if the condition is met, False otherwise.
        """
        if based_opt not in OPERATOR_MAP:
            raise ValueError(
                "Unknown operator %r. Valid operators: %s"
                % (based_opt, list(OPERATOR_MAP))
            )

        op = OPERATOR_MAP[based_opt]

        if based_amt == "percentage":
            base = credit_limit if rule_of == "credit_limit" else past_due_amt
            threshold = (base * value) / 100
            return op(past_due_amt, threshold)

        elif based_amt == "amount":
            return op(past_due_amt, value)

        else:
            raise ValueError(
                "Unknown based_amt %r. Expected 'percentage' or 'amount'." % based_amt
            )

    def calculate_due_amount(
        self, partner, operator_condition, record, days, partner_currency_id
    ):
        past_due_amt = 0.0
        cr = self.env.cr

        # myTime = datetime.strptime(str(sale_order.invoice_date or sale_order.date), DEFAULT_SERVER_DATETIME_FORMAT).date()

        order_date = (
            getattr(record, "date_order", None)
            or getattr(record, "invoice_date", None)
            or getattr(record, "date", None)
            or fields.Date.today()
        )
        myTime = (
            order_date
            if not isinstance(order_date, str)
            else datetime.strptime(order_date, "%Y-%m-%d").date()
        )
        check_date = myTime - timedelta(days=days)
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
                    AND (account_account.account_type IN ('asset_receivable'))
                    AND (l.partner_id = %s)
                    AND l.company_id = %s
                    AND l.amount_residual > 0.00
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

        return past_due_amt

    def check_approval_status(self, sale_order=None, move=None):
        # if move is None:
        #     move = sale_order
        record = sale_order or move

        past_due_amt = 0.0
        temp = False
        # account_invoice_obj = self.env["account.move"]
        partner = self.env["res.partner"]._find_accounting_partner(record.partner_id)
        # delivery_date = datetime.now().date()
        if not partner.credit_code_id:
            return super().check_approval_status(sale_order, move)
            # so_on_order_amount = 0
            # orders = self.env["sale.order"].search(
            #     [("partner_id", "=", partner.id), ("state", "=", "sale")]
            # )
            # for orderline in orders:
            #     so_on_order_amount += orderline.amount_total
            # total_amount = so_on_order_amount + record.amount_total
            # past_total_amount = past_due_amt + total_amount
            # if partner.credit_limit >= past_total_amount:
            #     return True, False
            # else:
            #     return False, False
        else:
            credit_check = partner.credit_code_id.credit_check
            if credit_check == "credit_hold":
                return False, True
            elif credit_check == "check_limit":
                return super().check_approval_status(sale_order, move)
                # past_due_amt = partner.credit
                # invoices = account_invoice_obj.search(
                #     [("partner_id", "=", partner.id), ("state", "=", "draft")]
                # )
                # for invoice in invoices:
                #     if invoice.invoice_payment_term_id:
                #         sign = 1 if invoice.is_inbound(include_receipts=True) else -1
                #         totlines = invoice.invoice_payment_term_id.with_context(
                #             currency_id=invoice.currency_id.id
                #         )._compute_terms(
                #             invoice.amount_total,
                #             invoice.invoice_date,
                #             invoice.company_id,
                #             invoice.amount_tax,
                #             invoice.amount_untaxed * sign,
                #             sign,
                #             invoice.amount_untaxed_signed,
                #             invoice.amount_untaxed * sign,
                #         )
                #         if invoice.invoice_date and invoice.amount_total:
                #             for total_line in totlines:
                #                 date = datetime.strptime(
                #                     total_line[0], "%m/%d/%Y"
                #                 ).date()
                #                 if delivery_date >= date:
                #                     past_due_amt += total_line[1]
                #                 elif invoice.move_type == "out_invoice":
                #                     past_due_amt += total_line[1]
                #                 elif invoice.move_type == "out_refund":
                #                     past_due_amt -= total_line[1]
                #     else:
                #         if (
                #             invoice.invoice_date_due
                #             and delivery_date >= invoice.invoice_date_due
                #         ):
                #             if invoice.move_type == "out_invoice":
                #                 past_due_amt += invoice.amount_total
                #             elif invoice.move_type == "out_refund":
                #                 past_due_amt -= invoice.amount_total
                # past_total_amount = past_due_amt + record.amount_total
                # if (
                #     record._name == "sale.order"
                #     and not record.pricelist_id.currency_id == partner.currency_id
                # ):
                #     past_total_amount = record.pricelist_id.currency_id._convert(
                #         past_total_amount, partner.currency_id
                #     )
                # return True if partner.credit_limit >= past_total_amount else False, False
            elif credit_check == "unlimited_account":
                return True, False
            elif credit_check == "base_on_rule":
                for rule_line in partner.credit_code_id.line_ids:
                    days = rule_line.days
                    if not rule_line.of:
                        past_due_amt = self.calculate_due_amount(
                            partner.id,
                            rule_line.operator_condition,
                            record,
                            days,
                            partner.currency_id,
                        )
                        if past_due_amt > 0.0:
                            temp = True
                        else:
                            temp = False
                    elif not temp and rule_line.of:
                        past_due_amt = self.calculate_due_amount(
                            partner.id,
                            rule_line.operator_condition,
                            record,
                            days,
                            partner.currency_id,
                        )
                        if past_due_amt > 0.0:
                            based_on = self.calculate_based_on(
                                partner.credit_limit,
                                past_due_amt,
                                rule_line.of,
                                rule_line.based_on_amount,
                                rule_line.operator_based_on,
                                rule_line.value,
                            )
                            if based_on:
                                temp = True
                            else:
                                temp = False
                if temp:
                    return False, True
                else:
                    if partner.credit_code_id.credit_limit_enforced:
                        past_due_amt = self.calculate_onorder_amount(
                            partner.id, ">=", 0, sale_order, partner.currency_id
                        )
                        past_total_amount = past_due_amt + record.amount_total
                        return (
                            True
                            if partner.credit_limit >= past_total_amount
                            else False,
                            False,
                        )
                    else:
                        return True, False


class CreditCodeLine(models.Model):
    _name = "credit.code.line"
    _description = "Credit Code Line"
    _order = "sequence"

    sequence = fields.Integer("Sequence", required=True, default=5)
    credit_code_id = fields.Many2one("credit.code", "Credit Code", ondelete="cascade")
    name = fields.Char(compute="_compute__get_name")
    check_past = fields.Selection(
        [("past_due", "Past Due")],
        "Check Past",
        required=True,
        default="past_due",
        help="Check type of amount.",
    )
    operator_condition = fields.Selection(
        [("==", "="), ("<=", "<="), ("<", "<"), (">=", ">="), (">", ">")],
        "Operator Condition",
        required=True,
        default="<=",
        help="Operator condition",
    )
    days = fields.Integer(
        "Days", required=True, help="Number of days used for calculate past due amount."
    )
    of = fields.Selection(
        [("past_due", "Past Due"), ("credit_limit", "Credit Limit")],
        "Of",
        help="Check limit based on past due amount or credit limit.",
    )
    based_on_amount = fields.Selection(
        [("percentage", "Percentage"), ("amount", "Amount")],
        "Based on Amount",
        help="Based on amount like percentage or fixed amount.",
    )
    operator_based_on = fields.Selection(
        [("==", "="), ("<=", "<="), ("<", "<"), (">=", ">="), (">", ">")],
        "Operator Based on",
        help="Operator condition",
    )
    value = fields.Float(
        "Value",
        help="Value fill based on amount selection like percentage or fixed amount.",
    )

    @api.depends(
        "check_past",
        "operator_condition",
        "operator_based_on",
        "value",
        "of",
        "days",
        "based_on_amount",
    )
    def _compute__get_name(self):
        for rule in self:
            if rule.of:
                if rule.of == "credit_limit":
                    of = "Credit Limit"
                else:
                    of = "Past Due"
                name = " if %s %s %s days then approval needed on %s %s %s %s." % (
                    rule.check_past,
                    rule.operator_condition,
                    rule.days,
                    of,
                    rule.based_on_amount,
                    rule.operator_based_on,
                    rule.value,
                )
            else:
                name = " if %s %s %s days then approval needed on any amount." % (
                    rule.check_past,
                    rule.operator_condition,
                    rule.days,
                )

            rule.name = name

    @api.onchange("of")
    def onchange_of_selection(self):
        if not self.of:
            self.based_on_amount = False
            self.operator_based_on = False
            self.value = False


class AccountInvoice(models.Model):
    _inherit = "account.move"

    @api.onchange("invoice_payment_term_id", "invoice_date")
    def _onchange_payment_term_date_invoice(self):
        invoice_date = self.invoice_date or self.date or fields.Date.today()

        if not self.invoice_payment_term_id:
            self.invoice_date_due = invoice_date
            return

        payment_term_record = self.invoice_payment_term_id
        sign = 1 if self.is_inbound(include_receipts=True) else -1

        term_lines = payment_term_record._compute_terms(
            date_ref=invoice_date,
            currency=self.currency_id,
            tax_amount_currency=self.amount_tax * sign,
            tax_amount=self.amount_tax_signed,
            untaxed_amount_currency=self.amount_untaxed * sign,
            untaxed_amount=self.amount_untaxed_signed,
            company=self.company_id,
            sign=sign,
        )

        # In Odoo 18, _compute_terms returns a list of dicts directly
        due_dates = [
            line["date"] for line in term_lines.get("line_ids") if line.get("date")
        ]

        self.invoice_date_due = max(due_dates) if due_dates else invoice_date
