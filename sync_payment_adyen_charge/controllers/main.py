# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.

import logging

from odoo import http
from odoo.http import request

from odoo.addons.account.controllers import portal
from odoo.addons.payment_adyen.controllers.main import AdyenController
from odoo.addons.payment import utils as payment_utils


_logger = logging.getLogger(__name__)


class PortalAccount(portal.PortalAccount):
    # def _invoice_get_page_view_values(
    #     self, invoice, access_token, payment=False, **kwargs
    # ):
    #     values = super()._invoice_get_page_view_values(invoice, access_token, **kwargs)
    #     latest_tx = invoice.transaction_ids[-1] if invoice.transaction_ids else False
    #     if latest_tx and latest_tx.fees and latest_tx.provider_code == "adyen":
    #         fees_amount = latest_tx.fees
    #         pm_code = (
    #             latest_tx.payment_method_id.primary_payment_method_id.code
    #             if latest_tx.payment_method_id.primary_payment_method_id
    #             else latest_tx.payment_method_id.code
    #         )
    #         provider_code = latest_tx.provider_code
    #         return {
    #             **values,
    #             "fees_amount": fees_amount,
    #             "pm_code": pm_code,
    #             "provider_code": provider_code,
    #         }
    #     else:
    #         fees_amount = None
    #         return values

    def _invoice_get_page_view_values(
        self, invoice, access_token, payment=False, **kwargs
    ):
        values = super()._invoice_get_page_view_values(invoice, access_token, **kwargs)
        latest_tx = invoice.transaction_ids[-1] if invoice.transaction_ids else False
        is_installment = request.params.get("is_installment")
        amount_custom = request.params.get("amount")
        values["is_installment"] = (
            True
            if is_installment and str(is_installment).lower() in ["1", "true"]
            else False
        )
        if values["is_installment"]:
            try:
                amount_custom = float(amount_custom)
                values["amount_custom"] = amount_custom
            except Exception as e:
                _logger.warning(" Could not parse custom amount: %s", e)
                amount_custom = invoice.amount_residual
        else:
            amount_custom = invoice.amount_residual

        full_amount = invoice.amount_residual
        partial_amount = float(amount_custom or 0) if values["is_installment"] else 0

        adyen_provider = (
            values.get("providers_sudo", request.env["payment.provider"])
            .sudo()
            .filtered(lambda p: p.code == "adyen")
        )
        card_payment_method = (
            values.get("payment_methods_sudo", request.env["payment.method"])
            .sudo()
            .filtered(lambda m: m.code == "card")
        )
        if adyen_provider and card_payment_method:
            # partner_country = (
            #     invoice.partner_id.country_id or adyen_provider.company_id.country_id
            # )
            currency_id = invoice.currency_id
            partner_id = invoice.partner_id.id
            pm = adyen_provider.payment_method_ids.filtered(lambda m: m.code == "card")[
                :1
            ]
            values["pm_sudo"] = pm
            full_fee = adyen_provider.compute_fees(
                pm_sudo=pm,
                amount=full_amount,
                currency=currency_id,
                partner_id=partner_id,
            )
            partial_fee = (
                adyen_provider.compute_fees(
                    pm_sudo=pm,
                    amount=partial_amount,
                    currency=currency_id,
                    partner_id=partner_id,
                )
                if partial_amount
                else 0.0
            )
            fees_amount = partial_fee if values["is_installment"] else full_fee
            final_amount = (partial_amount or full_amount) + fees_amount
            # remaining_amount = (
            #     full_amount - partial_amount if values["is_installment"] else 0.0
            # )

            values.update(
                {
                    "fees_amount_card": round(fees_amount, 2),
                    "final_amount_with_fee": round(final_amount, 2),
                    "full_invoice_amount": round(full_amount, 2),
                    "full_invoice_fee_card": round(full_fee, 2),
                    "amount_custom": round(partial_amount, 2),
                }
            )

        else:
            values.update(
                {
                    "fees_amount_card": 0,
                    "final_amount_with_fee": full_amount,
                    "full_invoice_amount": full_amount,
                    "full_invoice_fee_card": 0,
                    "amount_custom": partial_amount,
                }
            )
        if latest_tx:
            pm_code = (
                latest_tx.payment_method_id.primary_payment_method_id.code
                if latest_tx.payment_method_id.primary_payment_method_id
                else latest_tx.payment_method_id.code
            )
            provider_code = latest_tx.provider_code
            values.update(
                {
                    "pm_code": pm_code,
                    "provider_code": provider_code,
                }
            )
        return values


class AdyenControllerFees(AdyenController):
    @http.route("/payment/adyen/payments", type="json", auth="public")
    def adyen_payments(
        self,
        provider_id,
        reference,
        converted_amount,
        currency_id,
        partner_id,
        payment_method,
        access_token,
        browser_info=None,
    ):
        # Get transaction
        tx_sudo = (
            request.env["payment.transaction"]
            .sudo()
            .search([("reference", "=", reference)], limit=1)
        )
        # Add fees to amount
        total_amount = tx_sudo.amount + (tx_sudo.fees or 0)
        converted_amount = payment_utils.to_minor_currency_units(
            total_amount, tx_sudo.currency_id
        )

        return super().adyen_payments(
            provider_id,
            reference,
            converted_amount,
            currency_id,
            partner_id,
            payment_method,
            access_token,
            browser_info,
        )