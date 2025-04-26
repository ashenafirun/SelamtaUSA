/** @odoo-module alias=theme_alan.Hotspot **/

import { _t } from "@web/core/l10n/translation";
import { Component, onMounted} from "@odoo/owl";
import { renderToElement } from "@web/core/utils/render";

export class Hotspot extends Component {
    static template = "theme_alan.HotspotProductSelector";
    static props = {
        close: Function,
        save: Function,
        select_tmpl_id: Number,
        select_tmpl_name: String,
        modalRef: { type: Function, optional: true },
    }
    setup() {
        onMounted(() => this._select2());
        super.setup();
    }

    _procedureData(rec) {
        rec.forEach(ele => { ele['text'] = ele['name'] });
        return rec;
    }
    _select2(ev){
        let $input = $(this.__owl__.bdom.el).find("#as_search");
        $input.select2({
            width: "100%",
            placeholder:_t("Search Products..."),
            multiple: true,
            maximumSelectionSize: 1,
            dropdownCssClass: 'as-select2-dropdown',
            initSelection: function (ele, cbf) { },
            ajax: {
                url: "/select/data/fetch",
                quietMillis: 100,
                dataType: 'json',
                data: function (terms) {
                    return ({ terms:terms, searchIn: JSON.stringify(["product.template"]) });
                },
                results: (rec) => {
                    return {
                        results: this._procedureData(rec)
                    };
                },
            },
            formatResult: function (res) {
                return $(renderToElement("theme_alan.select2_fetch_info",{data:res}));
            },
            allowClear: true,
        });
        if(this.props.select_tmpl_id != undefined){
            $input.select2('data', {id:  this.props.select_tmpl_id, text: this.props.select_tmpl_name});
        }
    }
}


export class HotspotPopover extends Component {
    static template = "theme_alan.HotspotPopover";
    static props = {
        close: Function,
        data :{
            title: String,
            description: String,
            btn_txt: String,
            btn_url: String,
            img_url: String,
            pop_thm: String,
            pop_style: String
        }
    };
}

export class HotspotTranslation extends Component {
    static template = "theme_alan.HotspotTranslation";
    static props = {
        close: Function,
        add_transalte: Function,
        data :{
            lang_code_name: String,
            defaultTitle: String,
            defaultAtt: Array,
            key_data: String,
        }
    };
}

export default {
    Hotspot: Hotspot,
    HotspotPopover: HotspotPopover,
    HotspotTranslation: HotspotTranslation,
}