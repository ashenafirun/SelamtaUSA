# -*- coding: utf-8 -*-
"""Read this module's sync settings without needing Settings access.

The original code looked the settings up with
``env['res.config.settings'].search(...)``. Only users in
Administration / Settings may read that model, so any product or
category save by a regular user (including unarchiving a product)
failed with an Access Error. The values themselves live in system
parameters (see ResConfigSettings.set_values), so read them there.
"""
from types import SimpleNamespace

_PREFIX = 'bi_advance_all_in_one_merge_orders.'
_KEYS = ('category_sync', 'product_sync', 'sync_category', 'sync_product')


def merge_settings(env):
    get_param = env['ir.config_parameter'].sudo().get_param
    return SimpleNamespace(**{
        key: get_param(_PREFIX + key) in ('True', '1')
        for key in _KEYS
    })
