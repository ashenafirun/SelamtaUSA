/** @odoo-module alias=theme_alan.MegaMenuCategory **/

import { Dialog } from "@web/core/dialog/dialog";
// import { alanTemplate } from "theme_alan.mixins";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
// import { SelectData } from "theme_alan.SelectData";
import { renderToElement } from "@web/core/utils/render";
import { Component, useRef,  useState, onMounted} from "@odoo/owl";

class SubCategory extends Component {
    static components = { Dialog };
    static template = 'theme_alan.m_sub_category';
    setup() {

        this.categ_val = useRef("as_sub_category_search");
        this.title = "Select Category";
        this.footer = false;
        this.header = true;
        this.search = "product.public.category"
        this.props.selected_cat = [];
        onMounted(this._select2);
    }


    _select2(ev){
        let $input = $(this.__owl__.bdom.refs.modalRef).find("#as_sub_category_search")
        let self = this;
        $input.select2({
            width: "100%",
            tokenSeparators:[","],
            multiple: true,
            minimumInputLength: 2,
            maximumSelectionSize: 100,
            dropdownCssClass: 'as-select2-dropdown',
            allowClear: true,
            ajax: {
                url: "/select/data/fetch",
                quietMillis: 100,
                dataType: 'json',
                data: function (terms) {
                    return ({ terms:terms, searchIn:JSON.stringify([self.search]), parent_category:self.props.parent_id});
                },
                results: function (rec) {
                    return {
                        results: self._procedureData(rec)
                    };
                },
            },

            formatResult: function (res) {
                return $(renderToElement("theme_alan.select2_fetch_info",{data:res}));
            },
        });
        $input.select2('container').find('ul.select2-choices');

        this._init_selection($input, this.props.pre_selected_vals)

    }
    _procedureData(rec) {
        rec.forEach(ele => { ele['text'] = ele['name'] });
        return rec;
    }
    async _init_selection($input, vals){
        if(vals != "" && vals != undefined){
            let type_ids = vals.split(",")
            let details = await rpc('/get_records_details',{'record_ids':type_ids, 'model':"product.public.category"});
            for (const cats of details) {
                this.props.selected_cat.push({'id':cats['id'],'text':cats['name']})
            }
        }
        $input.select2('data', this.props.selected_cat)
    }


    _selectionDone(ev){
        let $input =  $(this.categ_val.el).val()
        $(ev.target).attr("data-subcat",$input);
        this.props._submit_second_category($input);
        this.props.close();
    }
}

export default {
    SubCategory: SubCategory
}
