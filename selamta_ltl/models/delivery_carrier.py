# -*- coding: utf-8 -*-
from odoo import fields, models

from .ltl_common import DEFAULT_CLOSE_TIME, DEFAULT_READY_TIME


class DeliveryCarrier(models.Model):
    """LTL settings on a shipping method, and the hooks carrier connections implement.

    A carrier connection module adds its own provider to ``delivery_type`` (for example
    ``tforce``) and defines any of these methods, named after it:

    ``<type>_ltl_rate(shipment)``
        Return a list of rates, each a dict with ``total`` (float, required) and optionally
        ``service``, ``transit_days``, ``quote_number``, ``expires`` (date), ``charges``
        (list of ``{'code', 'name', 'amount'}``).
    ``<type>_ltl_book(shipment, rate)``
        Book the shipment using one rate dict from ``<type>_ltl_rate``. Return a dict with
        any of ``pro_number``, ``bol_number``, ``pickup_number`` and ``documents``
        (list of ``(file name, bytes)``, e.g. the BOL PDF and labels).
    ``<type>_ltl_track(shipments)``
        Return ``{shipment.id: {...}}`` with any of ``state`` (``in_transit`` or
        ``delivered``), ``status`` (text), ``pro_number``, ``delivered_date``.
    ``<type>_ltl_documents(shipment)``
        Return a list of ``(file name, bytes)``: delivery receipt, weight & inspection
        certificate, invoice image...
    ``<type>_ltl_cancel(shipment)``
        Cancel the booked pickup with the carrier; raise UserError when the carrier refuses.
        Without it, Cancel only cancels the shipment in Odoo and staff call the carrier.

    Shipping methods without a connection still work: book on the carrier's website and
    type the PRO on the shipment.
    """
    _inherit = 'delivery.carrier'

    ltl_enabled = fields.Boolean(
        'LTL carrier', help='Offer this shipping method on LTL shipments and in the rate shop.')
    ltl_vendor_id = fields.Many2one(
        'res.partner', 'Bills come from',
        help='The vendor whose bills pay for this carrier\'s shipments, e.g. the carrier '
             'itself, or Priority1 for loads booked through Priority1. Carrier bills from '
             'this vendor are matched to shipments.')
    ltl_match_on = fields.Selection(
        [
            ('pro', 'PRO number'),
            ('bol', 'Our BOL number'),
            ('manual', 'Nothing in common - link bills by hand'),
        ],
        string='Match bills on', default='pro',
        help='Which number on our shipment appears as the bill reference on this vendor\'s '
             'bills. GlobalTranz bills on the BOL number; Priority1 and R+L bills carry '
             'their own invoice number, so those are linked by hand.')
    ltl_scac = fields.Char('SCAC', help='Carrier code printed on the BOL, e.g. XPOL, UPGF.')
    ltl_dock_open_time = fields.Float(
        'Dock opens', default=8.0, help='When our dock opens for this carrier (sent with pickups).')
    ltl_ready_time = fields.Float(
        'Freight usually ready at', default=DEFAULT_READY_TIME,
        help='Filled in on new shipments as the pickup ready time; change it per shipment.')
    ltl_close_time = fields.Float(
        'Dock usually closes at', default=DEFAULT_CLOSE_TIME,
        help='Filled in on new shipments as the time the dock closes; change it per shipment.')

    def _ltl_method(self, operation):
        self.ensure_one()
        return getattr(self, '%s_ltl_%s' % (self.delivery_type, operation), None)

    def ltl_can(self, operation):
        """True when this shipping method's connection supports the operation
        ('rate', 'book', 'track', 'documents' or 'cancel')."""
        self.ensure_one()
        return bool(self._ltl_method(operation))

    def ltl_rate(self, shipment):
        method = self._ltl_method('rate')
        return method(shipment) if method else []

    def ltl_book(self, shipment, rate):
        method = self._ltl_method('book')
        return method(shipment, rate) if method else {}

    def ltl_track(self, shipments):
        method = self._ltl_method('track')
        return method(shipments) if method else {}

    def ltl_documents(self, shipment):
        method = self._ltl_method('documents')
        return method(shipment) if method else []

    def ltl_cancel(self, shipment):
        method = self._ltl_method('cancel')
        return method(shipment) if method else False
