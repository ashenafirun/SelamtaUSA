# -*- coding: utf-8 -*-
"""Pre-assigned PRO blocks ("electronic PROs").

Some carriers (Daylight) reserve a block of PRO numbers for us, so the PRO can be printed
on our own BOL and pallet labels before pickup; the driver scans that barcode and the
freight moves under it. Daylight sends each block as one row: the first and last number
without the check digit, and how many. Odoo adds the check digit and hands out the next
unused PRO when a shipment with that carrier is booked.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .ltl_common import digits_only

CHECK_DIGITS = [
    ('luhn', 'Luhn mod 10 (Daylight)'),
    ('none', 'None: the numbers are full PROs'),
]
DEFAULT_WARN_BELOW = 200


def luhn_check_digit(base):
    """Check digit Daylight adds to a PRO (Luhn mod 10, Daylight's "Algorithm to calculate
    check digit"): from the right, double every other digit starting with the last one,
    add up the digits of the results and of the other digits, and take what brings the
    total up to a multiple of 10. '2191167' -> 2 (PRO 21911672)."""
    total = 0
    for position, char in enumerate(reversed(base)):
        digit = int(char)
        if position % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return (10 - total % 10) % 10


def full_pro(base, check_digit='luhn'):
    """The PRO for a block number: '18417750' -> '184177509'."""
    base = str(base)
    return base + str(luhn_check_digit(base)) if check_digit == 'luhn' else base


def pro_passes_check_digit(pro):
    """True when the last digit of the PRO is the Luhn check digit of the others."""
    pro = digits_only(pro)
    return len(pro) >= 2 and luhn_check_digit(pro[:-1]) == int(pro[-1])


class LtlProBlock(models.Model):
    _name = 'selamta.ltl.pro.block'
    _description = 'Pre-assigned PRO block'
    _order = 'carrier_id, id'

    name = fields.Char(compute='_compute_pros')
    carrier_id = fields.Many2one(
        'delivery.carrier', 'Carrier', required=True, ondelete='cascade', index=True,
        domain=[('ltl_enabled', '=', True)])
    first_base = fields.Char(
        'First number', required=True,
        help='First number of the block as the carrier sends it, without the check digit '
             '(FIRST_PRO on Daylight\'s sheet).')
    last_base = fields.Char(
        'Last number', required=True,
        help='Last number of the block, without the check digit (LAST_PRO on Daylight\'s sheet).')
    next_base = fields.Char(
        'Next number',
        help='The number Odoo hands out next, without the check digit. Empty starts at the '
             'first number. Set it past numbers already used elsewhere (FreightPOP, MyDaylight).')
    check_digit = fields.Selection(CHECK_DIGITS, 'Check digit', default='luhn', required=True)
    warn_below = fields.Integer(
        'Warn when fewer left', default=DEFAULT_WARN_BELOW,
        help='When fewer PROs than this are left for the carrier, booking posts a reminder on '
             'the shipment to ask the carrier for a new block.')
    active = fields.Boolean(default=True)
    note = fields.Char()
    first_pro = fields.Char('First PRO', compute='_compute_pros')
    last_pro = fields.Char('Last PRO', compute='_compute_pros')
    next_pro = fields.Char('Next PRO', compute='_compute_pros')
    quantity = fields.Integer('PROs', compute='_compute_counts', store=True)
    remaining = fields.Integer('Left', compute='_compute_counts', store=True)

    @api.depends('first_base', 'last_base', 'next_base', 'check_digit')
    def _compute_pros(self):
        for block in self:
            ok = block._numbers_ok()
            block.first_pro = full_pro(block.first_base, block.check_digit) if ok else False
            block.last_pro = full_pro(block.last_base, block.check_digit) if ok else False
            left = ok and block.next_base and int(block.next_base) <= int(block.last_base)
            block.next_pro = full_pro(block.next_base, block.check_digit) if left else False
            block.name = '%s - %s' % (block.first_pro, block.last_pro) if ok else _('New block')

    @api.depends('first_base', 'last_base', 'next_base')
    def _compute_counts(self):
        for block in self:
            if not block._numbers_ok():
                block.quantity = block.remaining = 0
                continue
            first, last = int(block.first_base), int(block.last_base)
            following = int(block.next_base) if block.next_base else first
            block.quantity = max(last - first + 1, 0)
            block.remaining = max(last - max(following, first) + 1, 0)

    def _numbers_ok(self):
        self.ensure_one()
        return all((value or '').isdigit() for value in (self.first_base, self.last_base)) \
            and (not self.next_base or self.next_base.isdigit())

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            for key in ('first_base', 'last_base', 'next_base'):
                if vals.get(key):
                    vals[key] = vals[key].strip()
            if not vals.get('next_base') and vals.get('first_base'):
                vals['next_base'] = vals['first_base']
        return super().create(vals_list)

    def write(self, vals):
        for key in ('first_base', 'last_base', 'next_base'):
            if vals.get(key):
                vals[key] = vals[key].strip()
        return super().write(vals)

    @api.constrains('first_base', 'last_base', 'next_base', 'carrier_id', 'active')
    def _check_numbers(self):
        for block in self:
            if not block._numbers_ok():
                raise ValidationError(_('PRO block numbers are digits only, without dashes or spaces.'))
            first, last = int(block.first_base), int(block.last_base)
            if first > last:
                raise ValidationError(_('The first number of a PRO block must not be after the last.'))
            if block.next_base and not first <= int(block.next_base) <= last + 1:
                raise ValidationError(_(
                    'The next number of block %(block)s must be between its first and last number.',
                    block=block.name))
            if not block.active:
                continue
            for other in self.search([('carrier_id', '=', block.carrier_id.id), ('id', '!=', block.id)]):
                if other._numbers_ok() and int(other.first_base) <= last and first <= int(other.last_base):
                    raise ValidationError(_(
                        'PRO block %(block)s overlaps block %(other)s of %(carrier)s.',
                        block=block.name, other=other.name, carrier=block.carrier_id.name))

    @api.model
    def _take_pro(self, carrier):
        """Hand out the next unused PRO of the carrier's blocks, oldest block first, or False
        when none is left. The block row is locked first, so two bookings at the same moment
        never get the same PRO. A number already on a shipment (typed by hand) is skipped.
        The number stays used even if the booking is later cancelled: it may be printed on
        a label already."""
        Shipment = self.env['selamta.ltl.shipment'].sudo()
        blocks = self.sudo().search([('carrier_id', '=', carrier.id), ('remaining', '>', 0)], order='id')
        for block in blocks:
            self.env.cr.execute('SELECT id FROM selamta_ltl_pro_block WHERE id = %s FOR UPDATE', [block.id])
            block.invalidate_recordset(['next_base'])
            start = block.next_base or block.first_base
            width, number, last = len(start), int(start), int(block.last_base)
            pro = False
            while number <= last and not pro:
                candidate = full_pro(str(number).zfill(width), block.check_digit)
                number += 1
                if not Shipment.search_count([('pro_digits', '=', candidate)], limit=1):
                    pro = candidate
            block.next_base = str(number).zfill(width)
            if pro:
                return pro
        return False

    @api.model
    def _left_for(self, carrier):
        """(PROs left, warning threshold) over the carrier's active blocks."""
        blocks = self.sudo().search([('carrier_id', '=', carrier.id)])
        return sum(blocks.mapped('remaining')), max(blocks.mapped('warn_below') or [0])
