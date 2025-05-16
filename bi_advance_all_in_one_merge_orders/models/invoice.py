# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
from datetime import datetime, timedelta, date
from odoo.tools import float_is_zero
import collections

from odoo.exceptions import UserError


class AccountInvoice(models.Model):
    _inherit = "account.move"

    @api.model
    def _get_invoice_key_cols(self):
        return [
            'partner_id', 'user_id', 'move_type', 'currency_id',
            'journal_id', 'company_id', 'partner_bank_id',
        ]

    @api.model
    def _get_invoice_line_key_cols(self):
        # fields = [
        #     'name',  'discount', 'tax_ids', 'price_unit',
        #     'product_id',  'analytic_account_id','account_id'
        # ]
        fields = [
            'name',  'discount', 'tax_ids', 'price_unit',
            'product_id', 'account_id'
        ]
        for field in ['sale_line_ids']:
            if field in self.env['account.move.line']._fields:
                fields.append(field)
                if 'subscription_id' in self.env['account.move.line']._fields:
                    fields.append('subscription_id')
        return fields

    # def _check_balanced(self, container):
    #     ''' Assert the move is fully balanced debit = credit.
    #     An error is raised if it's not the case.
    #     '''
    #     with self._disable_recursion(container, 'check_move_validity', default=True, target=False) as disabled:
    #         yield
    #         if disabled:
    #             return
    #
    #     unbalanced_moves = self._get_unbalanced_moves(container)
    #     if unbalanced_moves:
    #         error_msg = _("An error has occurred.")
    #         for move_id, sum_debit, sum_credit in unbalanced_moves:
    #             move = self.browse(move_id)
    #             error_msg += _(
    #                 "\n\n"
    #                 "The move (%s) is not balanced.\n"
    #                 "The total of debits equals %s and the total of credits equals %s.\n"
    #                 "You might want to specify a default account on journal \"%s\" to automatically balance each move.",
    #                 move.display_name,
    #                 format_amount(self.env, sum_debit, move.currency_id),
    #                 format_amount(self.env, sum_credit, move.currency_id),
    #                 move.journal_id.name)
    #         raise UserError(error_msg)

    @api.model
    def _get_first_invoice_fields(self, invoice):
        return {
            'invoice_origin': '%s' % (invoice.invoice_origin or '',),
            'partner_id': invoice.partner_id.id,
            'journal_id': invoice.journal_id.id,
            'user_id': invoice.user_id.id,
            'currency_id': invoice.currency_id.id,
            'company_id': invoice.company_id.id,
            'move_type': invoice.move_type,
            'state': 'draft',
            'ref': '%s' % (invoice.ref or '',),
            'name': '%s' % (invoice.name or '',),
            'fiscal_position_id': invoice.fiscal_position_id.id,
            'invoice_payment_term_id': invoice.invoice_payment_term_id.id,
            'invoice_line_ids': {},
            'partner_bank_id': invoice.partner_bank_id.id,
        }

    def do_merge(self, keep_references=True, date_invoice=False, currency_id=True,
                 remove_empty_invoice_lines=True):
        def make_key(br, fields):

            list_key = []
            for field in fields:
                field_val = getattr(br, field)
                if field in ('product_id'):
                    if not field_val:
                        field_val = False

                    if field_val:
                        field_val = field_val.id

                if field in ('account_id    '):
                    if not field_val:
                        field_val = False

                    if field_val:
                        field_val = field_val.id

                elif (isinstance(field_val, list) or
                      field == 'tax_ids' or
                      field == 'sale_line_ids'):
                    field_val = field_val
                list_key.append((field, field_val))
            list_key.sort()
            print('********============> list_key', list_key)
            return tuple(list_key)

        new_invoices = {}
        draft_invoices = [invoice
                          for invoice in self
                          if invoice.state == 'draft']
        required_element = [item for item, count in collections.Counter(
            draft_invoices).items() if count > 1]
        invoices = []
        if self._context.get('merge_type') == 'exist_1':
            for rec in draft_invoices:
                if required_element:
                    if rec == self._context.get('invoice_id') and rec == required_element[0]:
                        pass
                    else:
                        invoices.append(rec)
                else:
                    raise UserError(
                        _('Please Select Appropriate Invoice For Merge'))
            invoices.insert(0, required_element[0])
            invoices.append(required_element[0])

            seen_origins = {}
            seen_client_refs = {}
            account = []
            invoice_list = []

            for account_invoice in invoices:
                account.append(account_invoice.invoice_line_ids)
                invoice_list.append(account_invoice.id)

            for account_invoice in invoices:
                invoice_key = make_key(
                    account_invoice, self._get_invoice_key_cols())
                new_invoice = new_invoices.setdefault(invoice_key, ({}, []))
                origins = seen_origins.setdefault(invoice_key, set())
                client_refs = seen_client_refs.setdefault(invoice_key, set())
                new_invoice[1].append(account_invoice.id)
                invoice_infos = new_invoice[0]
                if not invoice_infos:
                    invoice_infos.update(
                        self._get_first_invoice_fields(account_invoice))
                    origins.add(account_invoice.invoice_origin)
                    client_refs.add(account_invoice.ref)
                    if not keep_references:
                        invoice_infos.pop('name')

                else:

                    if account_invoice.invoice_origin and account_invoice.invoice_origin not in origins:
                        invoice_infos['invoice_origin'] = (
                            invoice_infos['invoice_origin'] or '') + ' ' + account_invoice.invoice_origin
                        origins.add(account_invoice.invoice_origin)
                    if account_invoice.ref and account_invoice.ref not in client_refs:
                        invoice_infos['ref'] = (
                            invoice_infos['ref'] or '') + ' ' + account_invoice.ref
                        client_refs.add(account_invoice.ref)

                if self._context.get('merge_type') in ['exist_1', 'exist_2']:

                    for invoice_line in account_invoice.invoice_line_ids:
                        line_key = make_key(
                            invoice_line, self._get_invoice_line_key_cols())

                        o_line = invoice_infos['invoice_line_ids'].setdefault(
                            line_key, {})
                        if o_line:
                            if self._context.get('invoice_id') == account_invoice:
                                pass
                            else:

                                o_line['quantity'] += invoice_line.quantity
                        else:

                            o_line['quantity'] = invoice_line.quantity
                else:
                    for invoice_line in account_invoice.invoice_line_ids:
                        line_key = make_key(
                            invoice_line, self._get_invoice_line_key_cols())
                        o_line = invoice_infos['invoice_line_ids'].setdefault(
                            line_key, {})
                        if o_line:
                            o_line['quantity'] += invoice_line.quantity
                        else:
                            if len(invoice_list) == len(set(invoice_list)):
                                o_line['quantity'] = invoice_line.quantity
                            else:
                                o_line['quantity'] = 0
        else:
            seen_origins = {}
            seen_client_refs = {}
            account = []
            invoice_list = []
            for account_invoice in draft_invoices:
                account.append(account_invoice.invoice_line_ids)
                invoice_list.append(account_invoice.id)
            for account_invoice in draft_invoices:
                invoice_key = make_key(
                    account_invoice, self._get_invoice_key_cols())
                new_invoice = new_invoices.setdefault(invoice_key, ({}, []))
                origins = seen_origins.setdefault(invoice_key, set())
                client_refs = seen_client_refs.setdefault(invoice_key, set())
                new_invoice[1].append(account_invoice.id)
                invoice_infos = new_invoice[0]
                if not invoice_infos:
                    invoice_infos.update(
                        self._get_first_invoice_fields(account_invoice))
                    origins.add(account_invoice.invoice_origin)
                    client_refs.add(account_invoice.ref)
                    if not keep_references:
                        invoice_infos.pop('name')

                else:

                    if account_invoice.invoice_origin and account_invoice.invoice_origin not in origins:
                        invoice_infos['invoice_origin'] = (
                            invoice_infos['invoice_origin'] or '') + ' ' + account_invoice.invoice_origin
                        origins.add(account_invoice.invoice_origin)
                    if account_invoice.ref and account_invoice.ref not in client_refs:
                        invoice_infos['ref'] = (
                            invoice_infos['ref'] or '') + ' ' + account_invoice.ref
                        client_refs.add(account_invoice.ref)

                for invoice_line in account_invoice.invoice_line_ids:
                    line_key = make_key(
                        invoice_line, self._get_invoice_line_key_cols())
                    o_line = invoice_infos['invoice_line_ids'].setdefault(
                        line_key, {})
                    if o_line:
                        o_line['quantity'] += invoice_line.quantity
                    else:
                        if len(invoice_list) == len(set(invoice_list)):
                            o_line['quantity'] = invoice_line.quantity
                        else:
                            o_line['quantity'] = 0

        allinvoices = []
        allnewinvoices = []
        invoices_info = {}
        qty_prec = self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')
        for invoice_key, (invoice_data, old_ids) in new_invoices.items():
            if len(old_ids) < 2:
                allinvoices += (old_ids or [])
                continue
            for key, value in invoice_data['invoice_line_ids'].items():
                value.update(dict(key))

            for val in invoice_data['invoice_line_ids'].values():
                if val.get('sale_line_ids'):
                    param = val.get('sale_line_ids')[0]
                    val.update({
                        'sale_line_ids' : param
                    })
                if val.get('tax_ids'):
                    param = val.get('tax_ids')[0]
                    val.update({
                        'tax_ids' : param
                    })

            if remove_empty_invoice_lines:
                if self._context.get('merge_type') in ['exist_1', 'exist_2']:
                    invoice_data['invoice_line_ids'] = [
                        (0, 0, value) for value in
                        invoice_data['invoice_line_ids'].values()]
                else:
                    invoice_data['invoice_line_ids'] = [
                        (0, 0, value) for value in
                        invoice_data['invoice_line_ids'].values() if
                        not float_is_zero(
                            value['quantity'], precision_digits=qty_prec)]
            else:
                invoice_data['invoice_line_ids'] = [
                    (0, 0, value) for value in
                    invoice_data['invoice_line_ids'].values()]

            if date_invoice:
                invoice_data['date_invoice'] = date_invoice

            invoice_merge = self.env['invoice.merge'].search(
                [], order=' id desc', limit=1)
            if invoice_merge.types == 'new':
                newinvoice = self.with_context(
                    is_merge=True).create(invoice_data)
                invoice_merge = self.env['invoice.merge'].search(
                    [], order=' id desc', limit=1)
                total_amount = newinvoice.amount_untaxed
                final_amount = newinvoice.amount_total
                newinvoice.write({'currency_id': currency_id,
                                  'amount_untaxed': total_amount,
                                  'amount_total': final_amount})
                invoices_info.update({newinvoice.id: old_ids})
                allinvoices.append(newinvoice.id)
                allnewinvoices.append(newinvoice)

                old_invoices = self.env['account.move'].browse(old_ids)
                old_invoices.with_context(is_merge=True).button_cancel()
            if invoice_merge.types == 'exist_1':
                merge_with_id = self.env['account.move'].search(
                    [('id', '=', invoice_list[len(invoice_list)-1])])
                merge_with_id.invoice_line_ids.unlink()
                newinvoice = merge_with_id.write(invoice_data)
                total_amount = merge_with_id.amount_untaxed
                final_amount = merge_with_id.amount_total
                merge_with_id.write({'currency_id': currency_id,
                                     'amount_untaxed': total_amount,
                                     'amount_total': final_amount})
                invoices_info.update({merge_with_id.id: old_ids})
                allinvoices.append(merge_with_id.id)
                allnewinvoices.append(merge_with_id)

                cancel_invoice = self.env['account.move'].search(
                    [('id', 'in', invoice_list), ('id', '!=', invoice_list[len(invoice_list)-1])])
                cancel_invoice.with_context(is_merge=True).button_cancel()

    def do_merge_del(self, keep_references=True, date_invoice=False, currency_id=True,
                     remove_empty_invoice_lines=True):

        def make_key(br, fields):
            list_key = []
            for field in fields:
                field_val = getattr(br, field)
                if field in ('product_id'):
                    if not field_val:
                        field_val = False

                    if field_val:
                        field_val = field_val.id

                if field in ('account_id'):
                    if not field_val:
                        field_val = False

                    if field_val:
                        field_val = field_val.id

                elif (isinstance(field_val, list) or
                      field == 'tax_ids' or
                      field == 'sale_line_ids'):
                    field_val = tuple(
                        [(6, 0, tuple([v.id for v in field_val]))])
                list_key.append((field, field_val))
            list_key.sort()
            return tuple(list_key)

        new_invoices = {}
        draft_invoices = [invoice
                          for invoice in self
                          if invoice.state == 'draft']
        invoices = []
        required_element = [item for item, count in collections.Counter(
            draft_invoices).items() if count > 1]
        if self._context.get('merge_type') == 'exist_2':

            for rec in draft_invoices:
                if required_element:
                    if rec == self._context.get('invoice_id') and rec == required_element[0]:
                        pass
                    else:
                        invoices.append(rec)
                else:
                    raise UserError(
                        _('Please Select Appropriate Invoice For Merge'))

            invoices.insert(0, required_element[0])
            invoices.append(required_element[0])

            seen_origins = {}
            seen_client_refs = {}
            account = []
            invoice_list = []
            for account_invoice in invoices:
                account.append(account_invoice.invoice_line_ids)
                invoice_list.append(account_invoice.id)
            for account_invoice in invoices:
                invoice_key = make_key(
                    account_invoice, self._get_invoice_key_cols())
                new_invoice = new_invoices.setdefault(invoice_key, ({}, []))
                origins = seen_origins.setdefault(invoice_key, set())
                client_refs = seen_client_refs.setdefault(invoice_key, set())
                new_invoice[1].append(account_invoice.id)
                invoice_infos = new_invoice[0]
                if not invoice_infos:
                    invoice_infos.update(
                        self._get_first_invoice_fields(account_invoice))
                    origins.add(account_invoice.invoice_origin)
                    client_refs.add(account_invoice.ref)
                    if not keep_references:
                        invoice_infos.pop('name')

                else:

                    if account_invoice.invoice_origin and account_invoice.invoice_origin not in origins:
                        invoice_infos['invoice_origin'] = (
                            invoice_infos['invoice_origin'] or '') + ' ' + account_invoice.invoice_origin
                        origins.add(account_invoice.invoice_origin)
                    if account_invoice.ref and account_invoice.ref not in client_refs:
                        invoice_infos['ref'] = (
                            invoice_infos['ref'] or '') + ' ' + account_invoice.ref
                        client_refs.add(account_invoice.ref)

                if self._context.get('merge_type') in ['exist_1', 'exist_2']:

                    for invoice_line in account_invoice.invoice_line_ids:
                        line_key = make_key(
                            invoice_line, self._get_invoice_line_key_cols())
                        # print('********============> line_key', line_key)
                        o_line = invoice_infos['invoice_line_ids'].setdefault(
                            line_key, {})
                        # print('********============> o_line', o_line)
                        if o_line:
                            if self._context.get('invoice_id') == account_invoice:
                                pass
                            else:

                                o_line['quantity'] += invoice_line.quantity
                        else:

                            o_line['quantity'] = invoice_line.quantity
                else:
                    for invoice_line in account_invoice.invoice_line_ids:
                        line_key = make_key(
                            invoice_line, self._get_invoice_line_key_cols())
                        o_line = invoice_infos['invoice_line_ids'].setdefault(
                            line_key, {})
                        if o_line:

                            o_line['quantity'] += invoice_line.quantity
                        else:

                            if len(invoice_list) == len(set(invoice_list)):
                                o_line['quantity'] = invoice_line.quantity
                            else:
                                o_line['quantity'] = 0
        else:
            seen_origins = {}
            seen_client_refs = {}
            invoice_merge = self.env['invoice.merge'].search(
                [], order=' id desc', limit=1)

            count = 0
            account = []
            invoice_list = []
            for account_invoice in draft_invoices:
                account.append(account_invoice.invoice_line_ids)
                invoice_list.append(account_invoice.id)
            for account_invoice in draft_invoices:
                invoice_key = make_key(
                    account_invoice, self._get_invoice_key_cols())
                new_invoice = new_invoices.setdefault(invoice_key, ({}, []))
                origins = seen_origins.setdefault(invoice_key, set())
                client_refs = seen_client_refs.setdefault(invoice_key, set())
                new_invoice[1].append(account_invoice.id)
                invoice_infos = new_invoice[0]
                if not invoice_infos:
                    invoice_infos.update(
                        self._get_first_invoice_fields(account_invoice))
                    origins.add(account_invoice.invoice_origin)
                    client_refs.add(account_invoice.ref)
                    if not keep_references:
                        invoice_infos.pop('name')
                else:
                    if account_invoice.invoice_origin and account_invoice.invoice_origin not in origins:
                        invoice_infos['invoice_origin'] = (
                            invoice_infos['invoice_origin'] or '') + ' ' + account_invoice.invoice_origin
                        origins.add(account_invoice.invoice_origin)
                    if account_invoice.ref and account_invoice.ref not in client_refs:
                        invoice_infos['ref'] = (
                            invoice_infos['ref'] or '') + ' ' + account_invoice.ref
                        client_refs.add(account_invoice.ref)

                if self._context.get('merge_type') in ['exist_1', 'exist_2']:

                    for invoice_line in account_invoice.invoice_line_ids:
                        line_key = make_key(
                            invoice_line, self._get_invoice_line_key_cols())

                        o_line = invoice_infos['invoice_line_ids'].setdefault(
                            line_key, {})
                        if o_line:
                            if self._context.get('active_id') == account_invoice.id:
                                pass
                            else:

                                o_line['quantity'] += invoice_line.quantity
                        else:

                            o_line['quantity'] = invoice_line.quantity
                else:
                    for invoice_line in account_invoice.invoice_line_ids:
                        line_key = make_key(
                            invoice_line, self._get_invoice_line_key_cols())
                        o_line = invoice_infos['invoice_line_ids'].setdefault(
                            line_key, {})
                        if o_line:
                            o_line['quantity'] += invoice_line.quantity
                        else:
                            if len(invoice_list) == len(set(invoice_list)):
                                o_line['quantity'] = invoice_line.quantity
                            else:
                                o_line['quantity'] = 0

        allinvoices = []
        allnewinvoices = []
        invoices_info = {}
        qty_prec = self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')
        for invoice_key, (invoice_data, old_ids) in new_invoices.items():
            if len(old_ids) < 2:
                allinvoices += (old_ids or [])
                continue

            for key, value in invoice_data['invoice_line_ids'].items():
                value.update(dict(key))
            # print('********============> invoice_data[invoice_line_ids].values()', invoice_data['invoice_line_ids'].values())
            for val in invoice_data['invoice_line_ids'].values():
                if val.get('sale_line_ids'):
                    param = list(val.get('sale_line_ids')[0][2])
                    val.update({
                        'sale_line_ids' : [(6, 0, param)]
                    })
                if val.get('tax_ids'):
                    param = list(val.get('tax_ids')[0][2])
                    val.update({
                        'tax_ids' : [(6, 0, param)]
                    })

            if remove_empty_invoice_lines:
                if self._context.get('merge_type') in ['exist_1', 'exist_2']:
                    invoice_data['invoice_line_ids'] = [
                        (0, 0, value) for value in
                        invoice_data['invoice_line_ids'].values()]
                else:
                    invoice_data['invoice_line_ids'] = [
                        (0, 0, value) for value in
                        invoice_data['invoice_line_ids'].values() if
                        not float_is_zero(
                            value['quantity'], precision_digits=qty_prec)]

            else:
                invoice_data['invoice_line_ids'] = [
                    (0, 0, value) for value in
                    invoice_data['invoice_line_ids'].values()]

            if date_invoice:
                invoice_data['date_invoice'] = date_invoice
            # print('********============> invoice_data', invoice_data)
            invoice_merge = self.env['invoice.merge'].search(
                [], order=' id desc', limit=1)
            if invoice_merge.types == 'exist':
                newinvoice = self.with_context(
                    is_merge=True).create(invoice_data)
                invoice_merge = self.env['invoice.merge'].search(
                    [], order=' id desc', limit=1)
                total_amount = newinvoice.amount_untaxed
                final_amount = newinvoice.amount_total
                newinvoice.write({'currency_id': invoice_merge.currency_id.id,
                                  'amount_untaxed': total_amount,
                                  'amount_total': final_amount})
                invoices_info.update({newinvoice.id: old_ids})
                allinvoices.append(newinvoice.id)
                allnewinvoices.append(newinvoice)

                old_invoices = self.env['account.move'].browse(old_ids)
                old_invoices.with_context(is_merge=True).button_cancel()
            if invoice_merge.types == 'exist_2':
                merge_with_id = self.env['account.move'].search(
                    [('id', '=', invoice_list[len(invoice_list)-1])])
                merge_with_id.invoice_line_ids.unlink()
                newinvoice = merge_with_id.write(invoice_data)
                total_amount = merge_with_id.amount_untaxed
                final_amount = merge_with_id.amount_total
                merge_with_id.write({'currency_id': invoice_merge.currency_id.id,
                                     'amount_untaxed': total_amount,
                                     'amount_total': final_amount})
                invoices_info.update({merge_with_id.id: old_ids})
                allinvoices.append(merge_with_id.id)
                allnewinvoices.append(merge_with_id)

                cancel_invoice = self.env['account.move'].search(
                    [('id', 'in', invoice_list), ('id', '!=', invoice_list[len(invoice_list)-1])])
                cancel_invoice.with_context(is_merge=True).button_cancel()
        return invoice_infos
