/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";

patch(FormController.prototype,{
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
