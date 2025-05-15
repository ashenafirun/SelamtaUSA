/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";

patch(KanbanRenderer.prototype,{
    async validateQuickCreate(recordId, mode, group){
        super.validateQuickCreate(...arguments);
        await Promise.resolve();
        var changes = true
        var isKanban = true
        if ((!("popup" in user.context)) && recordId){
            rpc("/web/dataset/call_kw/user.recent.log/get_recent_log", {
                model: "user.recent.log",
                method: "get_recent_log",
                args: [this.props.list.model.config.resModel, recordId, changes,isKanban],
                kwargs: {},
            });
        }
    }
});
