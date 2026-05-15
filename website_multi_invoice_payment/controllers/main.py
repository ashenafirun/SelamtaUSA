# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.

from odoo import http, _
from odoo.http import request
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers.portal import PaymentPortal
from odoo.exceptions import ValidationError


class MultiInvoicePaymentPortal(PaymentPortal):
    @http.route(
        "/payment/pay",
        type="http",
        methods=["GET"],
        auth="public",
        website=True,
        sitemap=False,
    )
    def payment_pay(
        self,
        reference=None,
        amount=None,
        currency_id=None,
        partner_id=None,
        company_id=None,
        provider_id=None,
        access_token=None,
        **kwargs,
    ):
        inv_to_pay = {}
        for inv in kwargs.items():
            if inv[0].isdigit():
                inv_to_pay[int(inv[0])] = inv[1].replace(
                    ".", "", 1
                ).isdigit() and float(inv[1])
        if inv_to_pay:
            invoices = (
                request.env["account.move"]
                .sudo()
                .search([("id", "in", list(inv_to_pay.keys()))])
            )
            reference = ",".join(list(set([inv.name for inv in invoices])))
            amount = sum(inv_to_pay.values())
            request.session["invoice_to_pay"] = inv_to_pay
            currency_id = invoices and invoices[0].currency_id
        response = super(MultiInvoicePaymentPortal, self).payment_pay(
            reference=reference,
            amount=amount,
            currency_id=currency_id,
            partner_id=partner_id,
            company_id=company_id,
            provider_id=provider_id,
            access_token=access_token,
            **kwargs,
        )
        if inv_to_pay:
            response.qcontext.update(invoice_ids=list(inv_to_pay.keys()))
        return response

    @http.route("/payment/transaction", type="json", auth="public")
    def payment_transaction(
        self, amount, currency_id, partner_id, access_token, **kwargs
    ):
        """Create a draft transaction and return its processing values.

        :param float|None amount: The amount to pay in the given currency.
                                  None if in a payment method validation operation
        :param int|None currency_id: The currency of the transaction, as a `res.currency` id.
                                     None if in a payment method validation operation
        :param int partner_id: The partner making the payment, as a `res.partner` id
        :param str access_token: The access token used to authenticate the partner
        :param dict kwargs: Locally unused data passed to `_create_transaction`
        :return: The mandatory values for the processing of the transaction
        :rtype: dict
        :raise: ValidationError if the access token is invalid
        """
        # Check the access token against the transaction values
        amount = amount and float(
            amount
        )  # Cast as float in case the JS stripped the '.0'
        if not payment_utils.check_access_token(
            access_token, partner_id, amount, currency_id
        ):
            raise ValidationError(_("The access token is invalid."))
        kwargs.pop(
            "custom_create_values", None
        )  # Don't allow passing arbitrary create values
        invoice_ids = False
        if kwargs.get("reference_prefix"):
            list_of_invoice = kwargs.get("reference_prefix", False).split(",")
            invoice_ids = request.env["account.move"].search(
                [("name", "in", list_of_invoice)]
            )
        tx_sudo = self._create_transaction(
            amount=amount, currency_id=currency_id, partner_id=partner_id, **kwargs
        )
        if invoice_ids:
            tx_sudo.write({"invoice_ids": invoice_ids.ids})
        self._update_landing_route(tx_sudo, access_token)
        return tx_sudo._get_processing_values()
