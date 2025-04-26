/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { renderToElement } from "@web/core/utils/render";
import { Component, useRef,  useState, onMounted, onRendered, useSubEnv} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { UserInformDialog } from "theme_alan.UserInformDialog"

export class StaticSnippets extends Component {
    static components = { Dialog };
    static template = 'theme_alan.static_snippets';
    setup(){
        this.dialogService = useService("dialog");
        this.state = useState({
            'selected_templ_id':false
        })
    }
    selete_template(ev){
        let templ_id = $(ev.target).attr("data-temp");
        this.state.selected_templ_id = templ_id;
    }
    save(){
        if(this.state.selected_templ_id != false){
            const selected_snippet = 'theme_alan.'+ this.state.selected_templ_id
            this.props.snippet_builder.template_id = this.state.selected_templ_id
            const selected_template = renderToElement(selected_snippet)

            $(this.props.target).find("div").first().empty().append(selected_template);
            // $(this.props.target).find("div").first().replaceWith(selected_template);
            this.props.target.attr("data-snippet-name", this.props.snippet_builder.technical_name)
            .attr("data-size", 0)
            .attr("data-pos-id", 0)
            .attr("data-row-id", 0)
            .attr("data-active-id", 'as_slider')
            .attr("data-selected-templ-id", this.props.snippet_builder.template_id)
            .attr("data-default-content", true)
            .attr("data-design-edit", JSON.stringify(this.props.snippet_builder));
            this.props.close();
        }else{
            this.dialogService.add(UserInformDialog, {
                warning_msg:'Oops, Please select snippet.',
                inform_type:"no_snippet_config",
                onConfirm: async () => {
                    this.props.close();
                },
            });
        }
    }

}