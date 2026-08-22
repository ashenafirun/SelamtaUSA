{
    'name': 'Selamta - Pay Period Field Self-Read Access',
    'version': '18.0.1.0.0',
    'summary': 'Allow internal users to read x_hours_current_pay_period on their own profile',
    'description': """
Whitelists the custom field x_hours_current_pay_period on res.users so that a
user reading their own record still qualifies for Odoo's self-read elevation.

Without this, adding any non-whitelisted field to the user preferences form
causes res.users.read() to skip its sudo() elevation, and normal ACL then
rejects every HR-restricted field on the form (hours_last_month_display,
total_overtime, attendance_manager_id, barcode, birthday, ...) for any user
who is not an HR Officer.
    """,
    'author': 'Selamta L.L.C',
    'category': 'Human Resources',
    'depends': ['base', 'hr_attendance'],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
