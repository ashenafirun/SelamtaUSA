# -*- coding: utf-8 -*-
from odoo import fields, models


class SelamtaDeliveryService(models.Model):
    """What a customer's deliveries need, like the LTL extras carriers charge for:
    Liftgate Service, Residential Delivery, Limited Access Delivery. Staff can add more
    (Contacts > Configuration > Delivery services, or by typing a new one on a contact)."""
    _name = 'selamta.delivery.service'
    _description = 'Delivery service'
    _order = 'sequence, name, id'

    name = fields.Char('Delivery service', required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer('Color')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'This delivery service already exists.'),
    ]
