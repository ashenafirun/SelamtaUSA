# -*- coding: utf-8 -*-
import logging
import re

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.fields import Command
from odoo.osv import expression

_logger = logging.getLogger(__name__)

# Industries offered as "Type of business" on the website (data/industry_data.xml), in order.
WEBSITE_INDUSTRY_XMLIDS = [
    'selamta_registration.industry_restaurant',
    'selamta_registration.industry_grocery',
    'selamta_registration.industry_cafe',
    'selamta_registration.industry_caterer',
    'selamta_registration.industry_distributor',
    'selamta_registration.industry_other',
]

# Application answers kept on the business (company) record.
APPLICATION_FIELDS = [
    'selamta_application_state', 'selamta_application_date',
    'selamta_dba', 'selamta_receiving', 'selamta_receiving_hours',
    'selamta_delivery_address', 'selamta_invoice_email', 'selamta_resale_number',
    'selamta_referral', 'selamta_terms_accepted',
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    selamta_application_state = fields.Selection(
        [
            ('new', 'New - needs review'),
            ('approved', 'Approved'),
            ('rejected', 'Declined'),
        ],
        string='Wholesale application',
        copy=False, index=True, tracking=True,
        help="Set when the business applied on the website's wholesale registration page.",
    )
    selamta_application_date = fields.Datetime('Applied on', copy=False, readonly=True)
    selamta_application_contact_id = fields.Many2one(
        'res.partner', string='Applicant', compute='_compute_selamta_application_contact_id')
    selamta_dba = fields.Char('Store / restaurant name (DBA)')
    selamta_receiving = fields.Selection(
        [
            ('dock', 'Loading dock'),
            ('liftgate', 'No dock - needs a liftgate truck'),
            ('pickup', 'Picks up at the warehouse'),
        ],
        string='Receives deliveries by',
    )
    selamta_receiving_hours = fields.Char('Receiving days and hours')
    selamta_delivery_address = fields.Text('Delivery address (if different)')
    selamta_invoice_email = fields.Char('Email for invoices')
    selamta_resale_number = fields.Char('Sales tax / resale certificate number')
    selamta_referral = fields.Char('Heard about us from')
    selamta_terms_accepted = fields.Boolean('Accepted terms on application', copy=False)
    selamta_ein_document_ids = fields.Many2many(
        'ir.attachment', 'selamta_partner_ein_document_rel', 'partner_id', 'attachment_id',
        string='EIN letter / business license', copy=False,
    )
    selamta_resale_document_ids = fields.Many2many(
        'ir.attachment', 'selamta_partner_resale_document_rel', 'partner_id', 'attachment_id',
        string='Resale certificate', copy=False,
    )

    @api.depends('child_ids', 'child_ids.type', 'is_company')
    def _compute_selamta_application_contact_id(self):
        for partner in self:
            if partner.is_company:
                partner.selamta_application_contact_id = partner.child_ids.filtered(
                    lambda c: c.type == 'contact')[:1]
            else:
                partner.selamta_application_contact_id = partner

    @api.model
    def _selamta_website_industries(self):
        industries = self.env['res.partner.industry']
        for xmlid in WEBSITE_INDUSTRY_XMLIDS:
            industry = self.env.ref(xmlid, raise_if_not_found=False)
            if industry and industry.active:
                industries |= industry
        return industries

    # ------------------------------------------------------------------
    # Website form
    # ------------------------------------------------------------------

    def website_form_input_filter(self, request, values):
        """Called by the website form controller before the contact is created."""
        parent = getattr(super(), 'website_form_input_filter', None)
        if parent:
            values = parent(request, values)
        if 'selamta_application_state' not in values:
            return values
        # A visitor can never pre-approve themselves.
        values['selamta_application_state'] = 'new'
        values['selamta_application_date'] = fields.Datetime.now()
        if values.get('industry_id') not in self.sudo()._selamta_website_industries().ids:
            # only the business types offered on the page
            values.pop('industry_id', None)
        if values.get('vat'):
            values['vat'] = self._selamta_format_ein(values['vat'])
        for key in ('email', 'selamta_invoice_email'):
            if values.get(key):
                values[key] = values[key].strip().lower()
        for key in ('phone', 'mobile'):
            if key in values:
                # a lone "+1" (country code only) means the field was left empty
                values[key] = self._selamta_format_us_phone(values[key]) or False
        if values.get('zip'):
            values['zip'] = values['zip'].strip()
        if not values.get('country_id'):
            us = self.env.ref('base.us', raise_if_not_found=False)
            if us:
                values['country_id'] = us.id
        return values

    @api.model
    def _selamta_format_ein(self, value):
        digits = re.sub(r'\D', '', value or '')
        if len(digits) == 9:
            return '%s-%s' % (digits[:2], digits[2:])
        return (value or '').strip()

    @api.model
    def _selamta_format_us_phone(self, value):
        digits = re.sub(r'\D', '', value or '')
        if digits in ('', '1'):
            return ''
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]
        if len(digits) == 10:
            return '(%s) %s-%s' % (digits[:3], digits[3:6], digits[6:])
        return (value or '').strip()

    def _selamta_application_to_company(self):
        """Store a new application the way Selamta stores customers.

        The website form creates one contact (the person, with the business name
        as text). This creates the business as a company record with the EIN,
        address, industry and application answers, and files the person under it.
        Returns the company (or the contact unchanged if there is nothing to do).
        """
        self.ensure_one()
        person = self.sudo()
        if person.is_company or person.parent_id or not (person.company_name or '').strip():
            return person
        vals = {
            'name': person.company_name.strip(),
            'is_company': True,
            'vat': person.vat,
            'industry_id': person.industry_id.id,
            'phone': person.phone,
            'email': person.selamta_invoice_email or person.email,
            'website': person.website,
            'lang': person.lang,
        }
        vals.update(person._update_fields_values(person._address_fields()))
        vals.update(person._update_fields_values(APPLICATION_FIELDS))
        documents_ein = person.selamta_ein_document_ids
        documents_resale = person.selamta_resale_document_ids
        vals['selamta_ein_document_ids'] = [Command.set(documents_ein.ids)]
        vals['selamta_resale_document_ids'] = [Command.set(documents_resale.ids)]
        company = person.with_context(mail_create_nosubscribe=True).create(vals)
        (documents_ein | documents_resale).write({'res_id': company.id})

        clear = {name: False for name in APPLICATION_FIELDS}
        clear.update({
            'parent_id': company.id,
            'type': 'contact',
            'website': False,
            'selamta_ein_document_ids': [Command.clear()],
            'selamta_resale_document_ids': [Command.clear()],
        })
        person.write(clear)
        _logger.info('Wholesale application: company %s created for contact %s', company.id, person.id)
        return company

    # ------------------------------------------------------------------
    # Review
    # ------------------------------------------------------------------

    def action_selamta_application_approve(self):
        self.write({'selamta_application_state': 'approved'})
        return True

    def action_selamta_application_decline(self):
        self.write({'selamta_application_state': 'rejected'})
        return True

    def action_selamta_application_reopen(self):
        self.write({'selamta_application_state': 'new'})
        return True

    def _selamta_possible_duplicates(self):
        """Existing customers with the same EIN or email (shown to the reviewer)."""
        self.ensure_one()
        Partner = self.env['res.partner'].sudo().with_context(active_test=False)
        exclude = (self | self.child_ids).ids
        found = Partner
        digits = re.sub(r'\D', '', self.vat or '')
        if len(digits) == 9:
            candidates = Partner.search([('vat', 'ilike', digits[-4:]), ('id', 'not in', exclude)], limit=50)
            found |= candidates.filtered(lambda p: re.sub(r'\D', '', p.vat or '') == digits)
        emails = {e.strip() for e in [self.email] + self.child_ids.mapped('email') if e and e.strip()}
        if emails:
            domain = expression.OR([[('email', '=ilike', e)] for e in emails])
            found |= Partner.search(expression.AND([domain, [('id', 'not in', exclude)]]), limit=10)
        return found.mapped('commercial_partner_id')[:5]

    def _selamta_application_rows(self):
        """(label, value) pairs describing the application, for emails and notes."""
        self.ensure_one()
        contact = self.selamta_application_contact_id or self
        selection = lambda fname: dict(self._fields[fname]._description_selection(self.env)).get(self[fname])
        duplicates = self._selamta_possible_duplicates()
        rows = [
            (_('Business'), self.name if self.is_company else (self.company_name or self.name)),
            (_('Store name (DBA)'), self.selamta_dba),
            (_('Type of business'), self.industry_id.name),
            (_('EIN'), self.vat),
            (_('Contact'), contact.name if contact != self or not self.is_company else False),
            (_('Email'), contact.email),
            (_('Phone'), contact.phone or self.phone),
            (_('Mobile'), contact.mobile),
            (_('Address'), ', '.join(filter(None, [
                self.street, self.street2, self.city,
                ' '.join(filter(None, [self.state_id.code, self.zip])),
            ]))),
            (_('Receives deliveries by'), selection('selamta_receiving')),
            (_('Receiving hours'), self.selamta_receiving_hours),
            (_('Delivery address'), self.selamta_delivery_address),
            (_('Invoice email'), self.selamta_invoice_email),
            (_('Resale certificate no.'), self.selamta_resale_number),
            (_('Heard about us from'), self.selamta_referral),
            (_('Website'), self.website),
            (_('Documents'), ', '.join((self.selamta_ein_document_ids | self.selamta_resale_document_ids).mapped('name')) or _('none')),
            (_('Already in Odoo?'), '; '.join(duplicates.mapped('display_name'))),
        ]
        return [(label, value) for label, value in rows if value]

    def _selamta_notify_new_application(self):
        """Log the application on the business record and email the team."""
        for partner in self.sudo():
            rows = partner._selamta_application_rows()
            table = Markup('').join(
                Markup('<tr><td style="padding:4px 12px 4px 0;color:#555;vertical-align:top;">%s</td>'
                       '<td style="padding:4px 0;vertical-align:top;">%s</td></tr>') % (label, value)
                for label, value in rows
            )
            partner.message_post(
                body=Markup('<p>%s</p><table>%s</table>') % (
                    _('Wholesale application submitted on the website.'), table),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                author_id=self.env.ref('base.partner_root').id,
            )
            email_to = self.env['ir.config_parameter'].sudo().get_param(
                'selamta_registration.notify_email') or partner.env.company.email
            if not email_to:
                continue
            base_url = partner.get_base_url()
            link = '%s/odoo/wholesale-applications/%s' % (base_url, partner.id)
            business = partner.name if partner.is_company else (partner.company_name or partner.name)
            contact = partner.selamta_application_contact_id or partner
            body = Markup(
                '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1D2A22;">'
                '<p>%s</p><table style="border-collapse:collapse;">%s</table>'
                '<p style="margin-top:16px;"><a href="%s" style="background:#145A2A;color:#ffffff;'
                'padding:10px 18px;border-radius:6px;text-decoration:none;display:inline-block;">%s</a></p>'
                '</div>'
            ) % (
                _('A new business applied for a wholesale account:'),
                table, link, _('Review in Odoo'),
            )
            company = partner.env.company
            self.env['mail.mail'].sudo().create({
                'subject': _('New wholesale application: %s', business),
                'body_html': body,
                'email_to': email_to,
                'email_from': company.email_formatted or email_to,
                'reply_to': contact.email or False,
                'auto_delete': True,
            })
            _logger.info('Wholesale application %s (%s): notification queued to %s',
                         partner.id, escape(business), email_to)
