# -*- coding: utf-8 -*-
import logging
import re

from markupsafe import Markup, escape

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Fields the public registration form may write (see data/registration_setup.xml).
REGISTRATION_FORM_FIELDS = [
    'mobile', 'website',
    'selamta_application_state',
    'selamta_dba', 'selamta_business_type',
    'selamta_receiving', 'selamta_receiving_hours', 'selamta_delivery_address',
    'selamta_invoice_email', 'selamta_resale_number', 'selamta_referral',
    'selamta_terms_accepted',
    'selamta_ein_document_ids', 'selamta_resale_document_ids',
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
    selamta_dba = fields.Char('Store / restaurant name (DBA)')
    selamta_business_type = fields.Selection(
        [
            ('restaurant', 'Restaurant'),
            ('grocery', 'Grocery store / market'),
            ('cafe', 'Café / coffee shop'),
            ('caterer', 'Caterer / food service'),
            ('distributor', 'Wholesaler / distributor'),
            ('other', 'Other'),
        ],
        string='Business type',
    )
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

    def _selamta_application_rows(self):
        """(label, value) pairs describing the application, for emails and notes."""
        self.ensure_one()
        rows = [
            (_('Business'), self.company_name or self.commercial_company_name or self.name),
            (_('Store name (DBA)'), self.selamta_dba),
            (_('Business type'), dict(self._fields['selamta_business_type']._description_selection(self.env)).get(self.selamta_business_type)),
            (_('EIN'), self.vat),
            (_('Contact'), self.name),
            (_('Email'), self.email),
            (_('Phone'), self.phone),
            (_('Mobile'), self.mobile),
            (_('Address'), ', '.join(filter(None, [
                self.street, self.street2, self.city,
                ' '.join(filter(None, [self.state_id.code, self.zip])),
            ]))),
            (_('Receives deliveries by'), dict(self._fields['selamta_receiving']._description_selection(self.env)).get(self.selamta_receiving)),
            (_('Receiving hours'), self.selamta_receiving_hours),
            (_('Delivery address'), self.selamta_delivery_address),
            (_('Invoice email'), self.selamta_invoice_email),
            (_('Resale certificate no.'), self.selamta_resale_number),
            (_('Heard about us from'), self.selamta_referral),
            (_('Website'), self.website),
            (_('Documents'), ', '.join((self.selamta_ein_document_ids | self.selamta_resale_document_ids).mapped('name')) or _('none')),
        ]
        return [(label, value) for label, value in rows if value]

    def _selamta_notify_new_application(self):
        """Log the application on the contact and email the team."""
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
            business = partner.company_name or partner.name
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
                'reply_to': partner.email or False,
                'auto_delete': True,
            })
            _logger.info('Wholesale application %s (%s): notification queued to %s',
                         partner.id, escape(business), email_to)
