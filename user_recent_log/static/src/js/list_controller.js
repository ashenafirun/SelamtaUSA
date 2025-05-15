/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from '@web/views/list/list_controller';
import { user } from "@web/core/user";
import { rpc } from "@web/core/network/rpc";

patch(ListController.prototype,{
    async onRecordSaved(record, changes) {
        super.onRecordSaved(...arguments);
        await Promise.resolve();
        if ((!("popup" in user.context)) && Object.keys(changes || {}).length > 0){
            var def1 = rpc("/web/dataset/call_kw/user.recent.log/get_recent_log", {
                model: "user.recent.log",
                method: "get_recent_log",
                args: [record.resModel, record.resId, changes],
                kwargs: {},
            });
        }
    },
       
});
