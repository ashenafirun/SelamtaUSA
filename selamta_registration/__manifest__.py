# -*- coding: utf-8 -*-
{
    'name': 'Selamta Wholesale Registration',
    'version': '18.0.1.8.1',
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
* Delivery days and hours on every contact: a green bar under the name (hours and
  delivery services such as Liftgate Service, Residential Delivery, Limited Access
  Delivery; more can be added in Contacts > Configuration > Delivery services), edited
  in a "Deliveries" box on the Sales & Purchase tab and kept on the business for all
  its contacts. Install copies
  opening-hours tags (e.g. "OPEN 6 DAYS: 0800 A.M. - 0430 P.M.") into it once, and
  gives businesses with a residential tag the Residential Delivery service.
* "Approve and send login" on the application: sets the pricelist (Georgia / other
  states, chosen in Website > Settings > Wholesale registration), makes the business
  a customer, and sends Odoo's portal invitation so the applicant can set a password.

Install backs up the current page content; uninstalling restores it.
    """,
    'author': 'Selamta LLC',
    'license': 'LGPL-3',
    'depends': ['website_sale', 'mail', 'contacts'],
    'data': [
        'security/ir.model.access.csv',
        'data/registration_params.xml',
        'data/industry_data.xml',
        'data/delivery_service_data.xml',
        'views/registration_templates.xml',
        'views/delivery_service_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'data/registration_setup.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'selamta_registration/static/src/scss/registration.scss',
            'selamta_registration/static/src/js/registration.js',
        ],
        'web.assets_backend': [
            'selamta_registration/static/src/scss/partner_backend.scss',
        ],
        'web.assets_web_dark': [
            'selamta_registration/static/src/scss/partner_backend.dark.scss',
        ],
    },
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
