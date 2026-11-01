# -*- coding: utf-8 -*-
"""Shared constants and helpers for LTL freight."""
import re

# NMFC freight classes, lowest (densest, cheapest) to highest.
FREIGHT_CLASSES = [
    ('50', '50'), ('55', '55'), ('60', '60'), ('65', '65'), ('70', '70'),
    ('77.5', '77.5'), ('85', '85'), ('92.5', '92.5'), ('100', '100'), ('110', '110'),
    ('125', '125'), ('150', '150'), ('175', '175'), ('200', '200'), ('250', '250'),
    ('300', '300'), ('400', '400'), ('500', '500'),
]

UNIT_TYPES = [
    ('pallet', 'Pallet'),
    ('box', 'Box'),
]

# Commodity description a pallet or box line starts with (BOL and carrier APIs). Change it
# with the system parameter selamta_ltl.default_description; staff can edit it per line.
DEFAULT_DESCRIPTION = 'Foodstuff'

# Our pickup window when a carrier has none of its own: freight ready at 9:00 AM,
# dock closes at 5:30 PM (hours as floats, 17.5 = 17:30).
DEFAULT_READY_TIME = 9.0
DEFAULT_CLOSE_TIME = 17.5

# A bill reference shorter than this (after removing everything but digits) is too short
# to match safely.
MIN_REF_DIGITS = 5


def digits_only(value):
    """'476-103633' -> '476103633'; 'I123 45' -> '12345'; None -> ''."""
    return re.sub(r'\D', '', value or '')


def class_number(freight_class):
    """'77.5' -> 77.5; False/None -> None."""
    try:
        return float(freight_class) if freight_class else None
    except (TypeError, ValueError):
        return None


def match_strategies(ref_digits):
    """Ordered ways to compare a bill reference with a shipment reference.

    Returns a list of (label, operator, value) to use on the shipment's digits-only
    reference, in strict priority order (the 2026 freight audit rules). Always a list,
    never a set: where two shipments are both plausible, the order decides.
    """
    ref = ref_digits or ''
    if len(ref) < MIN_REF_DIGITS:
        return []
    strategies = [
        ('exact', '=', ref),
        # Our booking carries a check digit the bill leaves off (AAA Cooper 77637580-0
        # booked, 77637580 billed; Saia).
        ('check digit on booking', '=like', ref + '_'),
    ]
    if len(ref) - 1 >= MIN_REF_DIGITS:
        # The bill carries a check digit our booking leaves off.
        strategies.append(('check digit on bill', '=', ref[:-1]))
    if ref.startswith('1') and len(ref) - 1 >= MIN_REF_DIGITS:
        strategies.append(('leading 1 on bill', '=', ref[1:]))
    strategies.append(('leading 1 on booking', '=', '1' + ref))
    return strategies
