# -*- coding: utf-8 -*-
{
    'name': 'Selamta Wholesale Registration',
    'version': '18.0.1.5.0',
    'category': 'Website/Website',
    'summary': 'Wholesale account application page for selamtausa.com',
    'description': """
Redesigned "Open a Wholesale Account" page (/new-customer-registration):

* Clear intro (what you get, what you need, what happens next) and a grouped form
  built from ordinary website-builder blocks, so text and fields stay editable.
* Each application is saved like other customers: a company (business name, EIN,
  address, type of business in the standard Industry field) with the person as its
  contact. Extra answers kept on the company: store name (DBA), delivery days and
  hours (Monday to Friday buttons and time lists, 8 AM to 6 PM), delivery address,
  resale certificate number and documents, how they heard about us (dropdown), terms
  acceptance.
* ZIP code fills in city and state (built-in U.S. ZIP list, no outside service).
* Street address suggestions while typing (Google Places API (New); needs a key
  under Website > Settings > Wholesale registration).
* Own thank-you page, an email to the team for every new application, and a
  "Wholesale Applications" list under Website > eCommerce > Orders.
* "Approve and send login" on the application: sets the pricelist (Georgia / other
  states, chosen in Website > Settings > Wholesale registration), makes the business
  a customer, and sends Odoo's portal invitation so the applicant can set a password.

Install backs up the current page content; uninstalling restores it.
    """,
    'author': 'Selamta LLC',
    'license': 'LGPL-3',
    'depends': ['website_sale', 'mail'],
    'data': [
        'data/registration_params.xml',
        'data/industry_data.xml',
        'views/registration_templates.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'data/registration_setup.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'selamta_registration/static/src/scss/registration.scss',
            'selamta_registration/static/src/js/registration.js',
        ],
    },
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
