# -*- coding: utf-8 -*-
import hashlib
import logging

from lxml import etree

from odoo import api, fields, models

from .res_partner import REFERRAL_SOURCES

_logger = logging.getLogger(__name__)

REGISTRATION_URL = '/new-customer-registration'
CONTENT_TEMPLATE = 'selamta_registration.registration_page_content'
BACKUP_KEY = 'selamta_registration.backup_registration_page_%s'
HASH_PARAM = 'selamta_registration.page_hash.%s'
PATCH_PARAM = 'selamta_registration.page_patch_level.%s'
# Form field blocks that changed after the first version: (level, [(old input name, new input name)]).
# On a page edited in the builder, each level is applied once: those field blocks are
# swapped for the new ones and every other edit on the page is kept.
PAGE_PATCHES = [
    (1, [('selamta_business_type', 'industry_id')]),
    (2, [('selamta_receiving', 'selamta_receiving'),
         ('selamta_receiving_hours', 'selamta_receiving_hours'),
         ('selamta_delivery_address', 'selamta_delivery_address')]),
    (3, [('selamta_receiving', 'selamta_receiving'),
         ('selamta_receiving_hours', 'selamta_receiving_hours')]),
    # None = remove the field from the page
    (4, [('selamta_invoice_email', None),
         ('selamta_referral', 'selamta_referral')]),
]
PATCH_LEVEL = PAGE_PATCHES[-1][0]
# States offered in the form: the 50 states and DC (no territories / military).
US_STATE_CODES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'HI', 'ID', 'IL',
    'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE',
    'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD',
    'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
}


def _arch_hash(arch):
    return hashlib.sha1((arch or '').encode('utf-8')).hexdigest()


class Website(models.Model):
    _inherit = 'website'

    @api.model
    def _selamta_registration_setup(self):
        """Install / upgrade: put the new content on the registration page.

        The page is a normal website-builder page. Its content is replaced only if
        nobody edited it since the module last wrote it (same idea as
        selamta_homepage); the original content is kept in an inactive backup view
        that the uninstall hook restores.
        """
        websites = self.search([])
        for website in websites:
            website._selamta_registration_apply_page(create_if_missing=(website == websites[:1]))

    def _selamta_registration_render_content(self):
        self.ensure_one()
        us = self.env.ref('base.us')
        states = self.env['res.country.state'].search(
            [('country_id', '=', us.id), ('code', 'in', list(US_STATE_CODES))], order='name')
        industries = self.env['res.partner'].with_context(lang='en_US')._selamta_website_industries()
        html = self.env['ir.qweb'].with_context(lang='en_US')._render(CONTENT_TEMPLATE, {
            'states': states, 'us': us, 'industries': industries, 'website': self,
            'referral_options': REFERRAL_SOURCES,
        })
        return str(html)

    def _selamta_registration_page(self):
        self.ensure_one()
        Page = self.env['website.page'].with_context(active_test=False)
        return (
            Page.search([('url', '=', REGISTRATION_URL), ('website_id', '=', self.id)], limit=1)
            or Page.search([('url', '=', REGISTRATION_URL), ('website_id', '=', False)], limit=1)
        )

    @api.model
    def _selamta_registration_build_arch(self, base_arch, content_html):
        """Return base_arch with the children of #wrap replaced by content_html."""
        root = etree.fromstring(base_arch.encode('utf-8'))
        wraps = root.xpath("//*[@id='wrap']")
        if not wraps:
            raise ValueError('Registration page has no #wrap element')
        wrap = wraps[0]
        for child in list(wrap):
            wrap.remove(child)
        wrap.text = '\n'
        new = etree.fromstring(('<div>%s</div>' % content_html).encode('utf-8'))
        for child in list(new):
            wrap.append(child)
        return etree.tostring(root, encoding='unicode')

    def _selamta_registration_apply_page(self, create_if_missing=False):
        self.ensure_one()
        View = self.env['ir.ui.view'].with_context(active_test=False, lang='en_US')
        ICP = self.env['ir.config_parameter'].sudo()
        content = self._selamta_registration_render_content()
        page = self._selamta_registration_page()
        param = HASH_PARAM % self.id

        if not page:
            if not create_if_missing:
                return
            base = (
                '<t name="Open a Wholesale Account" t-name="selamta_registration.open_a_wholesale_account">'
                '<t t-call="website.layout"><div id="wrap" class="oe_structure oe_empty"/></t></t>'
            )
            view = View.create({
                'name': 'Open a Wholesale Account',
                'type': 'qweb',
                'key': 'selamta_registration.open_a_wholesale_account',
                'website_id': self.id,
                'arch': self._selamta_registration_build_arch(base, content),
            })
            self.env['website.page'].create({
                'url': REGISTRATION_URL,
                'view_id': view.id,
                'website_id': self.id,
                'is_published': True,
                'website_indexed': True,
            })
            ICP.set_param(param, _arch_hash(view.arch_db))
            ICP.set_param(PATCH_PARAM % self.id, str(PATCH_LEVEL))
            _logger.info('selamta_registration: created %s on website %s', REGISTRATION_URL, self.id)
            return

        view = page.view_id.with_context(lang='en_US')
        stored = ICP.get_param(param)
        if stored and stored != _arch_hash(view.arch_db):
            _logger.info('selamta_registration: %s was edited in the website builder; '
                         'leaving its content as it is', REGISTRATION_URL)
            self._selamta_registration_patch_fields(view, content)
            return

        backup_key = BACKUP_KEY % self.id
        if not View.search([('key', '=', backup_key)], limit=1):
            view.copy({
                'name': 'BACKUP %s %s (before selamta_registration)' % (fields.Date.today(), view.name),
                'key': backup_key,
                'active': False,
            })
        view.write({'arch': self._selamta_registration_build_arch(view.arch_db, content)})
        ICP.set_param(param, _arch_hash(view.arch_db))
        ICP.set_param(PATCH_PARAM % self.id, str(PATCH_LEVEL))
        _logger.info('selamta_registration: wrote new content to %s (view %s)', REGISTRATION_URL, view.id)

    def _selamta_registration_patch_fields(self, view, content_html):
        """Edited page: swap in only the field blocks changed since the last patch level."""
        ICP = self.env['ir.config_parameter'].sudo()
        level = int(ICP.get_param(PATCH_PARAM % self.id) or 0)
        todo = [pair for lvl, pairs in PAGE_PATCHES if lvl > level for pair in pairs]
        if not todo:
            return

        def field_block(root, input_name):
            inputs = root.xpath(
                ".//input[@name=$n] | .//select[@name=$n] | .//textarea[@name=$n]", n=input_name)
            if not inputs:
                return None
            blocks = inputs[0].xpath(
                "ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' s_website_form_field ')][1]")
            return blocks[0] if blocks else None

        root = etree.fromstring(view.arch_db.encode('utf-8'))
        new_root = etree.fromstring(('<div>%s</div>' % content_html).encode('utf-8'))
        changed = []
        for old_name, new_name in todo:
            old_block = field_block(root, old_name)
            if old_block is None:
                continue
            if new_name is None:
                parent = old_block.getparent()
                previous = old_block.getprevious()
                if old_block.tail:
                    if previous is not None:
                        previous.tail = (previous.tail or '') + old_block.tail
                    else:
                        parent.text = (parent.text or '') + old_block.tail
                parent.remove(old_block)
                changed.append(old_name)
                continue
            new_block = field_block(new_root, new_name)
            if new_block is None:
                continue
            new_block.tail = old_block.tail
            old_block.getparent().replace(old_block, new_block)
            changed.append(old_name)
        if changed:
            # The stored hash is left alone on purpose: the page still counts as
            # edited, so later upgrades keep the builder changes.
            view.write({'arch': etree.tostring(root, encoding='unicode')})
            _logger.info('selamta_registration: updated form field(s) %s on the edited page %s',
                         ', '.join(changed), REGISTRATION_URL)
        ICP.set_param(PATCH_PARAM % self.id, str(PATCH_LEVEL))

    def _selamta_registration_restore_page(self):
        """Uninstall: put the backed-up content back."""
        self.ensure_one()
        View = self.env['ir.ui.view'].with_context(active_test=False, lang='en_US')
        backup = View.search([('key', '=', BACKUP_KEY % self.id)], limit=1)
        page = self._selamta_registration_page()
        if backup and page:
            page.view_id.with_context(lang='en_US').write({'arch': backup.arch_db})
            _logger.info('selamta_registration: restored %s from backup view %s', REGISTRATION_URL, backup.id)
        if backup:
            backup.unlink()
        self.env['ir.config_parameter'].sudo().search(
            [('key', 'in', [HASH_PARAM % self.id, PATCH_PARAM % self.id])]).unlink()
