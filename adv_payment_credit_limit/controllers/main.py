# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import werkzeug
from psycopg2.errors import LockNotAvailable
from odoo import _, http, fields
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale as WebsiteSaleBase
from odoo.addons.website_sale.controllers.payment import PaymentPortal as WebsiteSalePaymentPortal
from odoo.addons.payment.controllers.portal import PaymentPortal
from odoo.exceptions import AccessError, MissingError, ValidationError, UserError
from odoo.fields import Command
from odoo.tools import SQL


_logger = logging.getLogger(__name__)


class WebsiteSale(WebsiteSaleBase):
    def _get_shop_payment_values(self, order, **kwargs):
        values = super()._get_shop_payment_values(order, **kwargs)

        payment_option = request.params.get("payment_option")
        values["payment_option"] = int(payment_option) if payment_option else 1

        partner = order.partner_id
        available_balance = partner.remaining_credit_limit if partner else 0.0

        is_unlimited_account = (
            bool(partner)
            and hasattr(partner, "credit_code_id")
            and partner.credit_code_id
            and partner.credit_code_id.credit_check == "unlimited_account"
        )

        credit_balance_exceeded = order.amount_total > available_balance

        company = request.website.company_id
        overdue_invoices = (
            request.env["account.move"]
            .sudo()
            .search(
                [
                    ("state", "not in", ["draft", "cancel"]),
                    ("move_type", "in", ["out_invoice", "out_receipt"]),
                    (
                        "payment_state",
                        "not in",
                        [
                            "in_payment",
                            "paid",
                            "reversed",
                            "blocked",
                            "invoicing_legacy",
                        ],
                    ),
                    ("invoice_date_due", "<", fields.Date.today()),
                    ("partner_id", "child_of", partner.commercial_partner_id.id),
                    ("company_id", "=", company.id),
                ]
            )
        )
        past_due_amount = sum(overdue_invoices.mapped("amount_residual"))
        show_past_due_option = (
            company.enable_past_due_notification and past_due_amount > 0
        )
        available_credit_to_use = min(
            available_balance,
            order.amount_total
        )
        remaining_amount = (
            order.amount_total - available_credit_to_use
            if available_credit_to_use > 0
            else 0.0
        )

        values.update(
            {
                "available_balance": available_balance,
                "credit_balance_exceeded": credit_balance_exceeded,
                "is_credit_exceed": credit_balance_exceeded,
                "show_credit_alert": credit_balance_exceeded,
                "is_unlimited_account": is_unlimited_account,
                "past_due_amount": past_due_amount,
                "show_past_due_option": show_past_due_option,
                "available_credit_to_use": available_credit_to_use,
                "remaining_amount": remaining_amount,
                "allow_credit": available_credit_to_use > 0,
            }
        )

        return values

    @http.route("/sale/confirm/order", type="http", auth="public", website=True)
    def sale_confirm_order(self, **post):
        order = request.website.sale_get_order()
        order = order.sudo()
        if not order:
            last_order_id = request.session.get("sale_last_order_id")
            if last_order_id:
                order = request.env["sale.order"].sudo().browse(last_order_id)

        if not order or order.state not in ("draft", "sent"):
            return request.redirect("/shop/payment")

        # Ensure the order belongs to the current user
        if order.partner_id != request.env.user.partner_id:
            return request.redirect("/shop")

        order.sudo().with_context(send_email=True).action_confirm()

        partner = order.partner_id
        available_balance = partner.remaining_credit_limit if partner else 0.0

        # Preserve order ID in session before resetting cart
        request.session["sale_last_order_id"] = order.id
        request.website.sale_reset()

        try:
            return request.render(
                "adv_payment_credit_limit.adv_credit_website_layout",
                {
                    "order": order.sudo(),
                    "available_balance": available_balance,
                },
            )
        except Exception:
            _logger.exception(
                "Failed to render credit confirmation page for order %s", order.id
            )
            return request.redirect("/shop/confirmation")


class CreditLimitPaymentPortal(WebsiteSalePaymentPortal):
    """Override the shop payment transaction to support hybrid credit + payment
    provider checkout.

    When the JS sends ``use_credit_limit=True``, we:
    1. Re-validate the customer's credit balance at transaction-creation time.
    2. Compute the split: credit portion vs. payment-provider portion.
    3. Record the credit used on the sale order (``used_credit_amount``).
    4. Let the base flow create the transaction for only the remaining amount.
    """

    @http.route(
        '/shop/payment/transaction/<int:order_id>',
        type='json',
        auth='public',
        website=True,
    )
    def shop_payment_transaction(self, order_id, access_token, **kwargs):
        # Pop our custom key before the base validation runs (it is not in the
        # whitelist and would raise a ValidationError).
        use_credit_limit = kwargs.pop('use_credit_limit', False)

        if not use_credit_limit:
            # Standard flow — delegate entirely to the base controller.
            return super().shop_payment_transaction(
                order_id, access_token, **kwargs
            )

        # --- Hybrid credit + payment flow ---
        # Validate order access & lock (same as base)
        try:
            order_sudo = self._document_check_access(
                'sale.order', order_id, access_token
            )
            request.env.cr.execute(
                SQL(
                    'SELECT 1 FROM sale_order WHERE id = %s FOR NO KEY UPDATE NOWAIT',
                    order_id,
                )
            )
        except MissingError:
            raise
        except AccessError as e:
            raise ValidationError(_("The access token is invalid.")) from e
        except LockNotAvailable:
            raise UserError(_("Payment is already being processed."))

        if order_sudo.state == "cancel":
            raise ValidationError(_("The order has been cancelled."))

        order_sudo._check_cart_is_ready_to_be_paid()

        # Re-validate credit balance at transaction time (prevents race
        # conditions if credit changed between page load and payment submit).
        partner = order_sudo.partner_id
        available_balance = partner.remaining_credit_limit if partner else 0.0
        credit_to_use = min(available_balance, order_sudo.amount_total)

        if credit_to_use <= 0:
            # No credit available anymore — fall back to full payment.
            return super().shop_payment_transaction(
                order_id, access_token, **kwargs
            )

        remaining_amount = order_sudo.amount_total - credit_to_use

        if remaining_amount <= 0:
            # Credit covers the entire order — shouldn't happen because the
            # checkbox is hidden when credit >= order total, but handle
            # gracefully.
            raise UserError(
                _(
                    "Your credit balance covers the full order. "
                    "Please use the 'Use Credit Limit and Confirm Order' option instead."
                )
            )

        # Record the credit split on the sale order.
        # order_sudo.sudo().used_credit_amount = credit_to_use
        order_sudo.sudo().write({
            'used_credit_amount': credit_to_use,
            'is_credit_limit_used': True,
        })

        # Override the amount so the transaction is for the remaining balance
        # only.
        kwargs['amount'] = remaining_amount
        kwargs['partner_id'] = order_sudo.partner_invoice_id.id
        kwargs['currency_id'] = order_sudo.currency_id.id
        kwargs['sale_order_id'] = order_id

        self._validate_transaction_kwargs(kwargs, additional_allowed_keys=(
            'partner_id', 'currency_id', 'sale_order_id',
        ))

        compare_amounts = order_sudo.currency_id.compare_amounts
        if compare_amounts(order_sudo.amount_paid, order_sudo.amount_total) == 0:
            raise UserError(
                _("The cart has already been paid. Please refresh the page.")
            )

        if (kwargs.get('flow') == 'token'):
            request.update_context(delay_payment_request=True)

        tx_sudo = self._create_transaction(
            custom_create_values={'sale_order_ids': [Command.set([order_id])]},
            **kwargs,
        )

        request.session['__website_sale_last_tx_id'] = tx_sudo.id
        self._validate_transaction_for_order(tx_sudo, order_sudo)
        if kwargs.get('flow') == 'token':
            tx_sudo._send_payment_request()

        return tx_sudo._get_processing_values()

class MultiInvoicePaymentPortal(PaymentPortal):
    @http.route(
        "/payment/confirmation",
        type="http",
        methods=["GET"],
        auth="public",
        website=True,
    )
    def payment_confirm(self, tx_id, access_token, **kwargs):
        tx_id = self._cast_as_int(tx_id)
        if tx_id:
            tx_sudo = request.env["payment.transaction"].sudo().browse(tx_id)
            if not tx_sudo:
                raise werkzeug.exceptions.NotFound()

            # is_past_due_payment = tx_sudo.invoice_ids and not any(
            #     inv.line_ids.sale_line_ids for inv in tx_sudo.invoice_ids
            # )
            is_past_due_payment = any(
                inv.invoice_date_due
                and inv.invoice_date_due < fields.Date.today()
                and inv.state == "posted"
                for inv in tx_sudo.invoice_ids
            )

            if is_past_due_payment and tx_sudo.state == "done":
                request.session.pop("invoice_to_pay", None)
                return request.redirect("/shop/payment")

            return request.render("payment.confirm", qcontext={"tx": tx_sudo})

        return request.redirect("/my/home")
