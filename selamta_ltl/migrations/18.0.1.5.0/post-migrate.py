# -*- coding: utf-8 -*-
"""Pickup window 9:00 to 17:30 (was 10:00 to 16:00).

Carriers still on the old defaults move to the new ones; a time someone set on a carrier
on purpose is left alone. Shipments not booked yet that still carry the old 10:00-16:00
window move too, so the next booking goes out with 9:00-17:30.
"""
import logging

_logger = logging.getLogger(__name__)

OLD_READY, OLD_CLOSE = 10.0, 16.0
NEW_READY, NEW_CLOSE = 9.0, 17.5


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        "UPDATE delivery_carrier SET ltl_ready_time = %s WHERE ltl_ready_time = %s",
        (NEW_READY, OLD_READY))
    ready = cr.rowcount
    cr.execute(
        "UPDATE delivery_carrier SET ltl_close_time = %s WHERE ltl_close_time = %s",
        (NEW_CLOSE, OLD_CLOSE))
    close = cr.rowcount
    cr.execute(
        """UPDATE selamta_ltl_shipment
              SET pickup_ready_time = %s, pickup_close_time = %s
            WHERE state = 'draft' AND pickup_ready_time = %s AND pickup_close_time = %s""",
        (NEW_READY, NEW_CLOSE, OLD_READY, OLD_CLOSE))
    shipments = cr.rowcount
    _logger.info(
        'selamta_ltl: pickup window 9:00-17:30 on %s carrier ready times, %s close times '
        'and %s shipments not booked yet', ready, close, shipments)
