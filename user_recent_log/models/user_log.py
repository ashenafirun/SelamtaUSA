# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime, timedelta
import logging
import json

_logger = logging.getLogger(__name__)


class UserRecentLog(models.Model):
    _name = "user.recent.log"
    _description = "User Recent Log"
    _order = "last_visited_on desc"

    def get_record_name(self):
        for activity in self:
            activity.name = False
            if activity.model and activity.res_id:
                record = self.env[activity.model].browse(activity.res_id)
                activity.name = record.display_name

    name = fields.Char("Record", compute="get_record_name")
    model = fields.Char("Model")
    res_id = fields.Integer("Res ID")
    last_visited_on = fields.Datetime("Last Visited On")
    user_id = fields.Many2one("res.users", "User")
    activity = fields.Text("Activity")

    @api.model
    def get_record(self, model, res_id):
        return self.env[model].sudo().browse(res_id)

    @api.model
    def get_recent_log(self, model, res_id, changes=False, isKanban=False):
        res_id = int(res_id)
        if isinstance(changes, str):
            changes = json.loads(changes)
        record = self.get_record(model, res_id)
        current_time = datetime.now()
        user = self.env.user.id
        if not changes and model != "user.recent.log":
            self.sudo().create(
                {
                    "model": model,
                    "res_id": res_id,
                    "user_id": user,
                    "last_visited_on": current_time,
                }
            )
        if changes and model != "user.recent.log":
            recent_record = self.sudo().create(
                {
                    "model": model,
                    "res_id": res_id,
                    "user_id": user,
                    "last_visited_on": current_time,
                }
            )
            response_text = "Please find following User Activities: \n"
            if isKanban:
                record = self.env[model].sudo().browse(res_id)
                for key, value in record.read()[0].items():
                    key_value = "=".join([str(key), str(value)])
                    response_text += key_value + "\n"
            else:
                for key, value in changes.items():
                    key_value = "=".join([str(key), str(value)])
                    response_text += key_value + "\n"
            if response_text and recent_record:
                recent_record.activity = response_text

    def redirect_on_record(self):
        for activity in self:
            if activity.model and activity.res_id:
                record = self.env[activity.model].browse(activity.res_id)
                return {
                    "name": record.name,
                    "type": "ir.actions.act_window",
                    "res_model": activity.model,
                    "res_id": activity.res_id,
                    "view_mode": "form",
                    "target": "self",
                }

    @api.model
    def cron_autovacuum_user_recent_log(self, days=120):
        """Crone Job: autovacuum user recent log.

        Auto-vacuume user recent logs after 120 days on sheduler run.

        :return: None
        """

        deadline = datetime.now() - timedelta(days=days)
        # for data_model in data_models:
        records = self.env["user.recent.log"].search(
            [("create_date", "<=", deadline)]
        )
        records.unlink()
        _logger.info(
            "AUTOVACUUM - %d 'User Recent Log' records deleted", len(records)
        )
        return True
