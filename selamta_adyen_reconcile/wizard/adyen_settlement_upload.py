import base64

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..tools import settlement_csv


class AdyenSettlementUpload(models.TransientModel):
    _name = 'selamta.adyen.settlement.upload'
    _description = 'Upload Adyen Settlement Report'

    file = fields.Binary('Settlement report (CSV)', required=True)
    filename = fields.Char()

    def action_import(self):
        self.ensure_one()
        if not settlement_csv.batch_number_from_filename(self.filename or ''):
            raise UserError(_('Upload an Adyen file named settlement_detail_report_batch_<number>.csv.'))
        settlement = self.env['selamta.adyen.settlement']._create_from_csv(
            self.filename, base64.b64decode(self.file))
        settlement.action_process()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'selamta.adyen.settlement',
            'res_id': settlement.id,
            'view_mode': 'form',
            'target': 'current',
        }
