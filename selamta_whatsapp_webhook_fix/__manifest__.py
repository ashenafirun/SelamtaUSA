{
    'name': 'Selamta - WhatsApp Webhook Compatibility',
    'version': '18.0.1.0.1',
    'summary': 'Process incoming WhatsApp messages whose webhook payload lacks metadata.phone_number_id',
    'description': """
Meta's newer WhatsApp account / Messaging account structure delivers incoming
"messages" webhooks that the standard Odoo WhatsApp controller silently skips
because value.metadata.phone_number_id is not where it expects it.

This module keeps the standard behaviour and, only for verified webhooks the
standard code skipped, locates the messages/statuses in the payload and hands
them to Odoo's own processing (_process_messages / _process_statuses).
Unrecognised payloads are logged once at INFO level for diagnosis.
    """,
    'author': 'Selamta L.L.C',
    'category': 'Marketing/WhatsApp',
    'depends': ['whatsapp'],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
