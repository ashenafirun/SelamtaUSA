# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, exceptions, _
from odoo.exceptions import UserError


class InvoiceMerge(models.TransientModel):
    _name = "invoice.merge"
    _description = "Merge Partner Invoice"

    types = fields.Selection([
        ('new', 'New Invoice/Bill and Cancel Selected'),
        ('exist', 'New Invoice/Bill and Delete all selected Invoices'),
        ('exist_1', 'Merge Invoices/Bills on existing selected Invoice/Bill and cancel others'),
        ('exist_2', 'Merge Invoices/Bills on existing selected Invoice/Bill and delete others')],
        'Merge Option', default='new', required=True)
    invoice_type = fields.Selection(selection=[
        ('entry', 'Journal Entry'),
        ('out_invoice', 'Customer Invoice'),
        ('out_refund', 'Customer Credit Note'),
        ('in_invoice', 'Vendor Bill'),
        ('in_refund', 'Vendor Credit Note'),
        ('out_receipt', 'Sales Receipt'),
        ('in_receipt', 'Purchase Receipt'),
    ])
    order_to_merge = fields.Many2many('account.move', 'rel_invoice_to_merge', 
        'invoice_id', 'to_merge_id', 'Invoice to merge')
    currency_id = fields.Many2one('res.currency', string='Select Currency',
        default=lambda self: self.env.user.company_id.currency_id)
    keep_references = fields.Boolean('Keep references from original invoices', default=True)
    invoice_id = fields.Many2one('account.move', string='Merge with')
    date_invoice = fields.Date('Invoice Date')
    account_id = fields.Many2one('account.move', string='Invoice')

    @api.model
    def default_get(self, fields):
        res = super(InvoiceMerge, self).default_get(fields)
        invoice_obj = self.env['account.move'].browse(self._context.get('active_ids'))
        res['account_id'] = invoice_obj[0].id
        res['invoice_type'] = invoice_obj[0].move_type
        res['order_to_merge'] = [(6, 0, self._context.get('active_ids'))]
        return res

    @api.model
    def _dirty_check(self):
        if self.env.context.get('active_model', '') == 'account.move':
            ids = self.env.context['active_ids']
            if len(ids) < 2:
                raise UserError(
                    _('Please select multiple invoices to merge in the list '
                      'view.'))

            invs = self.env['account.move'].browse(ids)
            for d in invs:
                if d['state'] != 'draft':
                    raise UserError(
                        _('At least one of the selected invoices is %s!') %
                        d['state'])

                if d['company_id'] != invs[0]['company_id']:
                    raise UserError(
                        _('Not all invoices are at the same company!'))
                if d['partner_id'] != invs[0]['partner_id']:
                    raise UserError(
                        _('Not all invoices are for the same partner!'))
                if d['move_type'] != invs[0]['move_type']:
                    raise UserError(
                        _('Not all invoices are of the same type!'))
                if d['currency_id'] != invs[0]['currency_id']:
                    raise UserError(
                        _('Not all invoices are at the same currency!'))
                if d['journal_id'] != invs[0]['journal_id']:
                    raise UserError(
                        _('Not all invoices are at the same journal!'))
        return {}

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        res = super().get_view(view_id, view_type, **options)
        if view_type != 'form':
            return res
        self._dirty_check()
        return res

    def merge_invoices(self):

        self.ensure_one()
        self._dirty_check()
        context = self._context.copy()
        if self.types == 'new':
            context.update({'merge_type': 'new'})
            inv_obj = self.env['account.move']
            aw_obj = self.env['ir.actions.act_window']
            ids = self.env.context.get('active_ids', [])
            invoices = inv_obj.browse(ids)
            allinvoices = invoices.with_context(context).do_merge(keep_references=self.keep_references,
                                                                  currency_id=self.currency_id.id or '',
                                                                  date_invoice=self.date_invoice)

            xid = {
                'out_invoice': 'view_invoice_tree',
                'out_refund': 'view_invoice_tree',
                'in_invoice': 'view_invoice_tree',
                'in_refund': 'view_invoice_tree',
            }[invoices[0].move_type]
            action = aw_obj._for_xml_id('account.action_move_line_form')

        if self.types == 'exist':
            context.update({'merge_type': 'exist'})
            inv_obj = self.env['account.move']
            aw_obj = self.env['ir.actions.act_window']
            ids = self.env.context.get('active_ids', [])
            invoices = inv_obj.browse(ids)
            allinvoices = invoices.with_context(context).do_merge_del(keep_references=self.keep_references,
                                                                      currency_id=self.currency_id.id or '',
                                                                      date_invoice=self.date_invoice)

            xid = {
                'out_invoice': 'view_invoice_tree',
                'out_refund': 'view_invoice_tree',
                'in_invoice': 'view_invoice_tree',
                'in_refund': 'view_invoice_tree',
            }[invoices[0].move_type]
            action = aw_obj._for_xml_id('account.action_move_line_form')
            invoices.unlink()

        if self.types == 'exist_1':
            context.update({'merge_type': 'exist_1', 'invoice_id': self.invoice_id})
            inv_obj = self.env['account.move']
            aw_obj = self.env['ir.actions.act_window']
            ids = self.env.context.get('active_ids', [])
            ids.append(self.invoice_id.id)
            invoices = inv_obj.browse(ids)
            allinvoices = invoices.with_context(context).do_merge(keep_references=self.keep_references,
                                                                  currency_id=self.currency_id.id or '',
                                                                  date_invoice=self.date_invoice)
            xid = {
                'out_invoice': 'view_invoice_tree',
                'out_refund': 'view_invoice_tree',
                'in_invoice': 'view_invoice_tree',
                'in_refund': 'view_invoice_tree',
            }[invoices[0].move_type]
            action = aw_obj._for_xml_id('account.action_move_line_form')

        if self.types == 'exist_2':
            context.update({'merge_type': 'exist_2', 'invoice_id': self.invoice_id})
            inv_obj = self.env['account.move']
            aw_obj = self.env['ir.actions.act_window']
            ids = self.env.context.get('active_ids', [])
            ids.append(self.invoice_id.id)
            invoices = inv_obj.browse(ids)
            cancel_invoice = self.env['account.move'].search([('id', 'in', ids), ('id', '!=', ids[len(ids) - 1])])
            allinvoices = invoices.with_context(context).do_merge_del(keep_references=self.keep_references,
                                                                      date_invoice=self.date_invoice)
            xid = {
                'out_invoice': 'view_invoice_tree',
                'out_refund': 'view_invoice_tree',
                'in_invoice': 'view_invoice_tree',
                'in_refund': 'view_invoice_tree',
            }[invoices[0].move_type]
            action = aw_obj._for_xml_id('account.action_move_line_form')
            cancel_invoice.unlink()
