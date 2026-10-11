# -*- coding: utf-8 -*-


def uninstall_hook(env):
    """Put the registration page back the way it was before the module."""
    for website in env['website'].search([]):
        website._selamta_registration_restore_page()
