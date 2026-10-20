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

    def _post_standalone(self, payment, decline=False):
        charged = []

        def fake_send(tx):
            charged.append(tx.amount)
            if decline:
                tx._set_error("Refused")
            else:
                tx._set_done()

        with patch(ADYEN_SEND, autospec=True, side_effect=fake_send):
            payment.action_post()
        return charged

    def test_standalone_card_payment_books_fee(self):
        payment = self._standalone_payment(self._token(self.card))
        self.assertEqual(payment.card_fee_preview, 15.0, "the form shows the fee before confirming")
        charged = self._post_standalone(payment)

        self.assertEqual(charged, [515.0], "the card is charged amount + 3%, once")
        self.assertEqual(payment.card_fee_preview, 0.0)
        self.assertEqual(payment.amount, 515.0)
        self.assertIn(payment.state, ("in_process", "paid"))
        self.assertEqual(payment.move_id.state, "posted")
        self.assertEqual(self._fee_booked(payment), 15.0)
        receivable = payment.move_id.line_ids.filtered(lambda l: l.account_type == "asset_receivable")
        self.assertEqual(receivable.credit, 500.0, "only the amount itself is credited to the customer")
        tx = payment.payment_transaction_id
        self.assertEqual((tx.amount, tx.fees), (515.0, 15.0))
        self.assertTrue(tx.card_fee_on_payment)

    def test_standalone_card_payment_declined(self):
        payment = self._standalone_payment(self._token(self.card))
        self._post_standalone(payment, decline=True)
        self.assertEqual(payment.state, "canceled")
        self.assertFalse(payment.move_id)
        self.assertEqual(payment.amount, 500.0, "shown as typed")
        self.assertEqual(self._customer_balance(), 0.0)

    def test_standalone_card_payment_refund_takes_back_fee(self):
        payment = self._standalone_payment(self._token(self.card))
        self._post_standalone(payment)
        refund = self._refund(payment.payment_transaction_id, 515.0)
        self.assertEqual(self._fee_reversed(refund), 15.0)
        self.assertEqual(self._customer_balance(), 0.0)

    def test_standalone_card_payment_with_existing_entry_is_refused(self):
        """Fallback: a hand-entered payment we can't add the fee to is not charged."""
        payment = self._standalone_payment(self._token(self.card))
        payment._generate_journal_entry()
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

    def test_online_saved_card_charges_fee_once(self):
        invoice = self._invoice(1000.0)
        tx = self._create_transaction(
            "token",
            reference="tok-online-1",
            amount=500.0,
            currency_id=self.company_currency.id,
            payment_method_id=self.card.id,
            token_id=self._token(self.card).id,
            invoice_ids=[Command.set(invoice.ids)],
        )
        charged = []

        def fake_send(tx_):
            charged.append(tx_.amount)

        with patch(ADYEN_SEND, autospec=True, side_effect=fake_send):
            tx._send_payment_request()
        self.assertEqual(charged, [515.0])
        self.assertEqual(tx.amount, 500.0, "the amount is restored after the request")

        tx._set_done()
        tx._post_process()
        self.assertEqual(tx.payment_id.amount, 515.0)
        self.assertEqual(self._fee_booked(tx.payment_id), 15.0)
        self.assertEqual(invoice.amount_residual, 500.0)

    def test_customer_without_country_pays_domestic_fee(self):
        self.partner.country_id = False
        tx = self._online_tx(500.0)
        self.assertEqual(tx.fees, 15.0)

    # ---------- Register Payment without a saved card ----------

    def test_wizard_without_saved_card_has_no_fee(self):
        invoice = self._invoice(1000.0)
        wizard = self._wizard(invoice, amount=500.0, payment_method_line_id=self.adyen_line.id)
        self.assertEqual(wizard.card_fees, 0.0)
        wizard.action_create_payments()
        payment = self._last_card_payment()
        self.assertEqual(payment.amount, 500.0)
        self.assertEqual(self._fee_booked(payment), 0.0)
        self.assertEqual(invoice.amount_residual, 500.0)

    # ---------- refunds ----------

    def _refund(self, source_tx, amount):
        refund_tx = source_tx._create_child_transaction(amount, is_refund=True)
        self.assertEqual(refund_tx.fees, 0.0, "a refund never carries a new fee")
        refund_tx._set_done()
        refund_tx._post_process()
        return refund_tx.payment_id

    def _fee_reversed(self, payment):
        return sum(
            payment.move_id.line_ids.filtered(lambda l: l.account_id == self.fee_account).mapped("debit")
        )

    def _customer_balance(self):
        receivable = self.partner.with_company(self.env.company).property_account_receivable_id
        lines = self.env["account.move.line"].search([
            ("partner_id", "=", self.partner.commercial_partner_id.id),
            ("account_id", "=", receivable.id),
            ("parent_state", "=", "posted"),
        ])
        return sum(lines.mapped("balance"))

    def test_full_refund_takes_back_fee(self):
        invoice = self._invoice(1000.0)
        self._charge(invoice, self._token(self.card), amount=500.0)
        source_tx = self._last_card_payment().payment_transaction_id
        self.assertEqual(self._customer_balance(), 500.0)

        refund = self._refund(source_tx, 515.0)
        self.assertEqual(refund.amount, 515.0, "the card gets back amount + fee")
        self.assertEqual(self._fee_reversed(refund), 15.0)
        self.assertEqual(self._customer_balance(), 1000.0, "the customer owes the 500 again, not 515")

    def test_partial_refunds_take_back_fee_share(self):
        invoice = self._invoice(1000.0)
        self._charge(invoice, self._token(self.card), amount=500.0)
        source_tx = self._last_card_payment().payment_transaction_id

        first = self._refund(source_tx, 206.0)  # 40% of 515
        self.assertEqual(self._fee_reversed(first), 6.0)
        second = self._refund(source_tx, 309.0)  # the rest
        self.assertEqual(self._fee_reversed(second), 9.0)
        self.assertEqual(self._customer_balance(), 1000.0)

    def test_online_payment_refund_takes_back_fee(self):
        tx = self._online_tx(500.0)
        tx._set_done()
        tx._post_process()
        refund = self._refund(tx, 515.0)
        self.assertEqual(self._fee_reversed(refund), 15.0)
        self.assertEqual(self._customer_balance(), 0.0)

    def test_partial_capture_child_has_no_fee(self):
        tx = self._online_tx(500.0)
        child = tx._create_child_transaction(200.0)
        self.assertEqual(child.fees, 0.0)

    # ---------- sale orders ----------

    def _order(self, amount):
        product = self.env["product.product"].create({
            "name": "Order goods", "list_price": amount, "taxes_id": [Command.clear()],
        })
        return self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [Command.create({
                "product_id": product.id, "product_uom_qty": 1, "price_unit": amount, "tax_id": [],
            })],
        })

    def _order_tx(self, order, amount, reference):
        return self._create_transaction(
            "direct",
            reference=reference,
            amount=amount,
            currency_id=self.company_currency.id,
            payment_method_id=self.card.id,
            sale_order_ids=[Command.set(order.ids)],
        )

    def test_checkout_fee_goes_on_order(self):
        order = self._order(500.0)
        tx = self._order_tx(order, 500.0, "so-checkout-1")
        tx._set_done()
        tx._post_process()
        self.assertEqual(order.state, "sale")
        self.assertTrue(tx.card_fee_on_order)
        self.assertEqual(order.amount_total, 515.0, "the fee is a line on the order")
        self.assertEqual(tx.payment_id.amount, 515.0)
        self.assertEqual(self._fee_booked(tx.payment_id), 0.0, "not booked twice")

    def test_payment_on_confirmed_order_books_fee_on_payment(self):
        order = self._order(500.0)
        order.action_confirm()
        tx = self._order_tx(order, 500.0, "so-confirmed-1")
        tx._set_done()
        tx._post_process()
        self.assertFalse(tx.card_fee_on_order)
        self.assertEqual(order.amount_total, 500.0)
        self.assertEqual(tx.payment_id.amount, 515.0)
        self.assertEqual(self._fee_booked(tx.payment_id), 15.0)
