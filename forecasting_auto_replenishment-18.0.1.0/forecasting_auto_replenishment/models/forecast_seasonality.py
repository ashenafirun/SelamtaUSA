from odoo import models, fields, api

class ForecastSeasonality(models.Model):
    _name = 'forecast.seasonality'
    _description = 'Forecast Seasonality'
    _rec_name = 'seasonality_name'

    seasonality_name = fields.Char(string="Seasonality Name", required=True)
    line_ids = fields.One2many('forecast.seasonality.line', 'seasonality_id', string="Monthly Factors")


class ForecastSeasonalityLine(models.Model):
    _name = 'forecast.seasonality.line'
    _description = 'Forecast Seasonality Line'
    _order = 'month asc'

    seasonality_id = fields.Many2one('forecast.seasonality', required=True)
    month = fields.Selection([
        ('1',  'January'),
        ('2',  'February'),
        ('3',  'March'),
        ('4',  'April'),
        ('5',  'May'),
        ('6',  'June'),
        ('7',  'July'),
        ('8',  'August'),
        ('9',  'September'),
        ('10', 'October'),
        ('11', 'November'),
        ('12', 'December'),
    ], string="Month", required=True)
    factor = fields.Float(string="Factor", default=1.0)

    _sql_constraints = [
        ('unique_month', 'unique(seasonality_id, month)',
         'This month already exists in this seasonality profile.')
    ]

    @api.onchange('month')
    def _onchange_month(self):
        if self.month:
            duplicate = self.seasonality_id.line_ids.filtered(
                lambda l: l.month == self.month and l != self
            )
            if duplicate:
                self.month = False
                return {
                    'warning': {
                        'title': 'Duplicate Month',
                        'message': 'This month is already added.'
                    }
                }