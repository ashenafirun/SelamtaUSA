from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account_payment.tests.common import AccountPaymentCommon
from odoo.addons.payment_adyen.tests.common import AdyenCommon

# Stub the call to Adyen: record the amount sent and mark the charge as successful.
ADYEN_SEND = (
    "odoo.addons.payment_adyen.models.payment_transaction.PaymentTransaction"
    "._send_payment_request"
)


@tagged("post_install", "-at_install")
class TestCardFees(AdyenCommon, AccountPaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        if not company.country_id:
            company.country_id = cls.env.ref("base.us")
        cls.partner.country_id = company.country_id
        cls.company_currency = company.currency_id

        cls.provider.write({
            "journal_id": cls.company_data["default_journal_bank"].id,
            "fees_active": True,
            "fees_dom_var": 0.03,
            "fees_dom_fixed": 0.0,
        })
        cls.adyen_line = cls.provider.journal_id.inbound_payment_method_line_ids.filtered(
            lambda line: line.payment_provider_id == cls.provider
        )
        cls.bank_line = cls.company_data["default_journal_bank"].inbound_payment_method_line_ids.filtered(
            lambda line: not line.payment_provider_id
        )[:1]

        cls.fee_account = cls.company_data["default_account_revenue"].copy(
            {"name": "Card Surcharge Income", "code": "400100"}
        )
        fee_product = cls.env.ref("sync_payment_adyen_charge.product_product_payment_fees")
        fee_product.with_company(company).property_account_income_id = cls.fee_account
        cls.fee_product = fee_product

        cls.card = cls.env.ref("payment.payment_method_card")
        cls.ach = cls.env.ref("payment.payment_method_ach_direct_debit")

    # ---------- helpers ----------

    def _invoice(self, amount):
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "currency_id": self.company_currency.id,
            "invoice_date": "2026-10-01",
            "invoice_line_ids": [Command.create({
                "name": "Goods",
                "price_unit": amount,
                "quantity": 1,
                "tax_ids": [],
            })],
        })
        invoice.action_post()
        return invoice

    def _token(self, method):
        return self._create_token(payment_method_id=method.id, partner_id=self.partner.id)

    def _wizard(self, invoices, **values):
        return self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoices.ids,
        ).create(values)

    def _pay_by_bank(self, invoice, amount):
        """An earlier partial payment that is already applied to the invoice."""
        return self._wizard(
            invoice,
            amount=amount,
            journal_id=self.company_data["default_journal_bank"].id,
            payment_method_line_id=self.bank_line.id,
        )._create_payments()

    def _charge(self, invoices, token, **values):
        charged = []

        def fake_send(tx):
            charged.append(tx.amount)
            tx._set_done()

        with patch(ADYEN_SEND, autospec=True, side_effect=fake_send):
            wizard = self._wizard(
                invoices,
                payment_method_line_id=self.adyen_line.id,
                payment_token_id=token.id,
                **values,
            )
            wizard.action_create_payments()
        return charged

    def _fee_lines(self, invoices):
        return invoices.invoice_line_ids.filtered(lambda l: l.product_id == self.fee_product)

    def _last_card_payment(self):
        return self.env["account.payment"].search(
            [("payment_method_line_id", "=", self.adyen_line.id), ("state", "!=", "canceled")],
            order="id desc", limit=1,
        )

    def _fee_booked(self, payment):
        return sum(
            payment.move_id.line_ids.filtered(lambda l: l.account_id == self.fee_account).mapped("credit")
        )

    # ---------- staff charges from the invoice ----------

    def test_partial_charge_fee_on_amount_charged_and_earlier_payment_kept(self):
        invoice = self._invoice(1000.0)
        bank_payment = self._pay_by_bank(invoice, 100.0)
        self.assertEqual(invoice.amount_residual, 900.0)

        charged = self._charge(invoice, self._token(self.card), amount=500.0)

        self.assertEqual(charged, [515.0], "3% of the 500 charged, not of the 900 open")
        payment = self._last_card_payment()
        self.assertEqual(payment.amount, 515.0)
        self.assertEqual(payment.payment_transaction_id.fees, 15.0)
        self.assertEqual(self._fee_booked(payment), 15.0)
        self.assertFalse(self._fee_lines(invoice), "the invoice must not be modified")
        self.assertEqual(invoice.amount_residual, 400.0)
        bank_receivable = bank_payment.move_id.line_ids.filtered(
            lambda l: l.account_id == invoice.line_ids.filtered(
                lambda il: il.display_type == "payment_term").account_id
        )
        self.assertTrue(bank_receivable.reconciled, "the earlier payment stays applied")

    def test_second_partial_charge_also_pays_its_fee(self):
        invoice = self._invoice(1000.0)
        token = self._token(self.card)
        self.assertEqual(self._charge(invoice, token, amount=400.0), [412.0])
        self.assertEqual(self._charge(invoice, token, amount=600.0), [618.0])
        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertIn(invoice.payment_state, ("paid", "in_payment"))

    def test_several_invoices_grouped(self):
        invoices = self._invoice(300.0) + self._invoice(700.0)
        charged = self._charge(invoices, self._token(self.card), group_payment=True)
        self.assertEqual(charged, [1030.0])
        self.assertEqual(invoices.mapped("amount_residual"), [0.0, 0.0])
        self.assertEqual(self._fee_booked(self._last_card_payment()), 30.0)
        self.assertFalse(self._fee_lines(invoices))

    def test_full_single_invoice_card_payment(self):
        for amount_kwargs in ({"amount": 1000.0}, {}):
            invoice = self._invoice(1000.0)
            charged = self._charge(invoice, self._token(self.card), **amount_kwargs)
            self.assertEqual(charged, [1030.0])
            self.assertEqual(invoice.amount_residual, 0.0)

    def test_ach_token_has_no_fee(self):
        invoice = self._invoice(1000.0)
        charged = self._charge(invoice, self._token(self.ach), amount=1000.0)
        self.assertEqual(charged, [1000.0])
        self.assertEqual(invoice.amount_residual, 0.0)

    def test_declined_card_leaves_invoice_untouched(self):
        invoice = self._invoice(1000.0)
        self._pay_by_bank(invoice, 100.0)

        def decline(tx):
            tx._set_error("Refused")

        with patch(ADYEN_SEND, autospec=True, side_effect=decline):
            self._wizard(
                invoice,
                payment_method_line_id=self.adyen_line.id,
                payment_token_id=self._token(self.card).id,
                amount=500.0,
            ).action_create_payments()

        self.assertEqual(invoice.amount_residual, 900.0)
        self.assertFalse(self._fee_lines(invoice))

    # ---------- Accounting > Payments > New with a saved card ----------

    def _standalone_payment(self, token, amount=500.0):
        return self.env["account.payment"].create({
            "payment_type": "inbound",
            "partner_type": "customer",
            "amount": amount,
            "currency_id": self.company_currency.id,
            "partner_id": self.partner.id,
            "journal_id": self.provider.journal_id.id,
            "payment_method_line_id": self.adyen_line.id,
            "payment_token_id": token.id,
        })

    def test_standalone_card_payment_is_refused(self):
        payment = self._standalone_payment(self._token(self.card))
        with patch(ADYEN_SEND, autospec=True) as send:
            with self.assertRaises(UserError):
                payment.action_post()
            send.assert_not_called()

    def test_standalone_ach_payment_still_allowed(self):
        payment = self._standalone_payment(self._token(self.ach))
        charged = []

        def fake_send(tx):
            charged.append(tx.amount)
            tx._set_done()

        with patch(ADYEN_SEND, autospec=True, side_effect=fake_send):
            payment.action_post()
        self.assertEqual(charged, [500.0])

    # ---------- customer pays online ----------

    def _online_tx(self, amount, invoices=None):
        return self._create_transaction(
            "direct",
            amount=amount,
            currency_id=self.company_currency.id,
            payment_method_id=self.card.id,
            invoice_ids=[Command.set(invoices.ids)] if invoices else [],
        )

    def test_online_invoice_payment_fee_on_payment(self):
        invoice = self._invoice(1000.0)
        bank_payment = self._pay_by_bank(invoice, 100.0)
        tx = self._online_tx(500.0, invoice)
        self.assertEqual(tx.fees, 15.0)

        tx._set_done()
        tx._post_process()

        payment = tx.payment_id
        self.assertEqual(payment.amount, 515.0)
        self.assertEqual(self._fee_booked(payment), 15.0)
        self.assertFalse(self._fee_lines(invoice))
        self.assertEqual(invoice.amount_residual, 400.0)
        self.assertTrue(
            bank_payment.move_id.line_ids.filtered(lambda l: l.account_type == "asset_receivable").reconciled
        )

    def test_online_payment_without_document_books_fee(self):
        tx = self._online_tx(500.0)
        tx._set_done()
        tx._post_process()
        payment = tx.payment_id
        self.assertEqual(payment.amount, 515.0)
        self.assertEqual(self._fee_booked(payment), 15.0)
        receivable = payment.move_id.line_ids.filtered(lambda l: l.account_type == "asset_receivable")
        self.assertEqual(receivable.credit, 500.0, "only the amount itself is credited to the customer")
