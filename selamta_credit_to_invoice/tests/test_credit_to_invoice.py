from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.sale.tests.common import TestSaleCommon


@tagged('post_install', '-at_install')
class TestCreditToInvoice(TestSaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.account_use_credit_limit = True
        cls.customer = cls.partner_a
        cls.item = cls.company_data['product_order_no']

    def _confirmed_order(self, qty, price):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({
                'product_id': self.item.id,
                'product_uom_qty': qty,
                'price_unit': price,
                'tax_id': [Command.clear()],
            })],
        })
        order.action_confirm()
        return order

    def _invoice_short(self, order, qty):
        invoice = order._create_invoices()
        invoice.invoice_line_ids.quantity = qty
        invoice.action_post()
        return invoice

    def _credit_to_invoice(self):
        self.env.invalidate_all()
        return self.customer.credit_to_invoice

    def test_short_shipped_invoiced_order_is_not_counted(self):
        order = self._confirmed_order(10, 100.0)
        self.assertAlmostEqual(self._credit_to_invoice(), 1000.0)

        self._invoice_short(order, 6)
        # Standard Odoo still sees 4 units "to invoice" on the order...
        self.assertAlmostEqual(order.amount_to_invoice, 400.0)
        # ...but there are no backorders, so it is not credit exposure.
        self.assertAlmostEqual(self._credit_to_invoice(), 0.0)

    def test_uninvoiced_order_still_counts(self):
        self._confirmed_order(10, 100.0)
        closed = self._confirmed_order(5, 100.0)
        self._invoice_short(closed, 3)
        self.assertAlmostEqual(self._credit_to_invoice(), 1000.0)

    def test_draft_invoice_warning_amount(self):
        order = self._confirmed_order(10, 100.0)
        self._invoice_short(order, 6)
        # A second draft invoice on a closed order must not reduce exposure
        # below what the customer actually owes.
        draft = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'invoice_line_ids': [Command.create({
                'product_id': self.item.id,
                'quantity': 1,
                'price_unit': 100.0,
                'tax_ids': [Command.clear()],
                'sale_line_ids': [Command.set(order.order_line.ids)],
            })],
        })
        self.assertAlmostEqual(draft._get_partner_credit_warning_exclude_amount(), 0.0)
