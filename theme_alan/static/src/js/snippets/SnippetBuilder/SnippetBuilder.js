/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { renderToElement } from "@web/core/utils/render";
import { Component, useRef,  useState, onMounted} from "@odoo/owl";
import { FrameBuilder } from "../FrameBuilder/FrameBuilder";
import { makeDraggableHook } from "@web/core/utils/draggable_hook_builder_owl";
import { pick } from "@web/core/utils/objects";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { UserInformDialog } from "theme_alan.UserInformDialog"
import { StaticSnippets } from "../StaticSnippets/StaticSnippets";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { SubCategory } from "theme_alan.MegaMenuCategory"

const useDraggable = makeDraggableHook({
    name: "useDraggable",
    onComputeParams({ ctx }) { ctx.followCursor = false },
    onWillStartDrag: ({ ctx }) => pick(ctx.current, "element"),
    onDragStart: ({ ctx }) => pick(ctx.current, "element"),
    onDrag: ({ ctx }) => pick(ctx.current, "element"),
    onDragEnd: ({ ctx }) => pick(ctx.current, "element", "dropzone", "helper")
});

export class SnippetBuilder extends Component {
    static components = { Dialog, FrameBuilder };

    static template = 'theme_alan.snippet_builder';
    setup() {
        this.search_record = useRef("search_record");
        this.s_container = useRef("snippet_container");
        this.sortable_record = useRef("sortable_record");
        this.snippet_preview = useRef("snippet_preview");
        this.dialogService = useService("dialog");
        this.subCategory = useState({'second_level':[],'second_level_ids':[]});

        // Initialize state using useState hook
        this.editor = useState({
            "name": "Snippet",
            "technical_name": false,
            "design": false,
            "selection": false,
            "model": false,
            "view": ["slider", "grid"],
            "loop": true,
            "auto_slider": false,
            "slider_time": false,
            "default_col_desk": false,
            'slider_style':false,
            "default_col_mob": false,
            "pagination": "none",
            'default_stemplate_id': false,
            'default_gtemplate_id': false,
            'grid_layout_style': false,
            'slider_layout_style': false,
            "template_id": false,
            "allow_add_to_cart": false,
            "allow_quick_view": false,
            "allow_compare": false,
            "allow_wishlist": false,
            "allow_rating": false,
            "allow_label": false,
            "allow_hover_image": false,
            "allow_stock_info": false,
            "allow_offer_time": false,
            "allow_brand_info": false,
            "allow_color_variant": false,
            "record_limit": false,
            "quick_selection": false,
            'allow_link':false,
            'col_item':false
        });
        this.state = useState({'record_info':[], 'record_ids':[]})

        this.props.slider_styles = []
        this.props.grid_styles = []

         // Pagination Style
        this.props.pagination = [
             ['none', 'None'],
             ['simple', 'Simple'],
             ['dynamic', 'Dynamic'],
             ['progress_bar', 'Progress Bar'],
             ['fraction', 'Fraction'],
             ['scroll_bar', 'Scrollbar'],
             ['coverflow', 'Coverflow'],
             ['cards', 'Cards'],
         ]



        // Setup draggable
        useDraggable({
            ref: this.s_container,
            elements: ".s_item",
            // When drag starts
            onDragStart: (ctx) => {
            },
            // Before drag starts
            onWillStartDrag: ({ element, x, y }) => {},
            // During drag
            onDrag: ({ element, x, y }) => {
                $('#drag-clone').remove();
                const $clone = $(element).clone();
                $clone.attr('id', 'drag-clone')
                       .css({
                           "position": 'fixed',
                           "pointerEvents": 'none',
                           "opacity": 0.7,
                           "z-index": 999999,
                           "left": x,
                           "top": y
                       });
                $('body').append($clone);
            },
            onDrop: ({ element }) => {},
            // When drag ends
            onDragEnd: async ({ element, x, y }) => {
                $('#drag-clone').remove();
                this.snippet_drop(element, x, y)
            },
        });
    }
    _get_style_layouts(){
            // Pagination Style
            this.props.pagination = [
                ['none', 'None'],
                ['simple', 'Simple'],
                ['dynamic', 'Dynamic'],
                ['progress_bar', 'Progress Bar'],
                ['fraction', 'Fraction'],
                ['scroll_bar', 'Scrollbar'],
                ['coverflow', 'Coverflow'],
                ['cards', 'Cards'],
            ]
            // Slider Styles

            const TechnicalNames = ['categories_products', 'brand_products', 'CategoryProduct', 'BrandProduct'];
            let SliderStyle = "as-slider-"
            let GridStyle = "as-grid-"
            if (TechnicalNames.includes(this.editor.technical_name)) {
                SliderStyle = "as-tab-slider-"
                GridStyle = "as-tab-grid-"
            }
            if(this.props.snippet_type == "as_mega_menu"){
                if(this.editor.technical_name == "megamenu_products" || this.editor.technical_name == "MegaMenuProduct"){
                    SliderStyle = "as-mm-product-snippet-"
                    GridStyle = "as-mm-product-snippet-"
                }
                else if(this.editor.technical_name == "megamenu_category" || this.editor.technical_name == "MegaMenuCategory"){
                    SliderStyle = "as-mm-category-slider-"
                    GridStyle = "as-mm-category-grid-"
                }
                else{
                    SliderStyle = "as-mm-brand-snippet-"
                    GridStyle = "as-mm-brand-snippet-"
                }

            }
            const BannerSlider = ["product_banner", "ProductBanner"]

            var slider_layout_style = this.editor.slider_layout_style
            var slider_styles = []
            var slider_item = 5
            if(BannerSlider.includes(this.editor.technical_name)){
                slider_item = 3
            }

            for (var i = 1; i <= slider_item; i++) {
                slider_styles.push([
                    'Slider Style ' + i,
                    'theme_alan.' + slider_layout_style,
                    SliderStyle + i
                ]);
            }
            this.props.slider_styles = slider_styles;

            // Grid Styles
            var grid_layout_style = this.editor.grid_layout_style
            var grid_styles = []
            for (var i = 1; i <= 5; i++) {
                grid_styles.push([
                    'Grid Style ' + i,
                    'theme_alan.' + grid_layout_style,
                    GridStyle + i
                ]);
            }
            this.props.grid_styles = grid_styles;

    }
    async get_snippet_data(){
        if(this.state.record_ids != undefined){
            let details = await rpc('/get_records_details',{'record_ids':this.state.record_ids, 'model':this.editor.model})
            this.state.record_info = details;
        }
    }
    async handleclick(target){
        let recordIdsAttr = target.attr("data-records-ids")
        let designEdit = target.attr("data-design-edit");

        if(recordIdsAttr != undefined && designEdit != undefined){
            let designEditObj = JSON.parse(designEdit);
            Object.assign(this.editor, designEditObj);
            let records = JSON.parse(recordIdsAttr)
            this.state.record_ids = records
            await this.get_snippet_data();
            this._get_style_layouts();
            this._sortable();
        }
    }
    async _select2(){
        let $input = $(this.search_record.el);
        let self = this
        $input.select2({
                width: "100%",
                tokenSeparators:[","],
                minimumInputLength: 2,
                placeholder:_t("Search Items ...."),
                multiple: false,
                maximumSelectionSize: 100,
                dropdownCssClass: 'as-select2-dropdown',
                allowClear: true,
                initSelection: function (ele, cbf) { },
                ajax: {
                    url: "/select/data/fetch",
                    quietMillis: 100,
                    dataType: 'json',
                    data: function (terms) {
                        return ({ terms:terms, searchIn: JSON.stringify([self.editor.model]) });
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
        $input.on("select2-selecting", async (ev)=> {
            let $template = $(document.querySelector(".as-active-snippet-template"));
            if (!this.state.record_ids.includes(ev.val)) {
                this.state.record_ids.unshift(ev.val);
            }
            await this.get_snippet_data();
            await this.intialized_snippet($template, this.editor, false);
        });
    }
    _procedureData(rec) {
        rec.forEach(ele => { ele['text'] = ele['name'] });
        return rec;
    }

    async snippet_drop(element, x, y){
        let technical_name = $(element).attr("data-snippet");
        let getEditor = this.props.snippets.find(snippet => snippet.technical_name === technical_name);
        let dropTarget = document.elementFromPoint(x, y);
        dropTarget = dropTarget?.closest(".as-snippet-drop-container")
        if (dropTarget) {
            Object.assign(this.editor, { ...getEditor });
            await this.intialized_snippet(dropTarget, getEditor, true)
            await this._select2()
        }
    }
    async intialized_snippet(dropTarget, getEditor, initDrop){

        const isStaticSnippet = ["static_snippets", "StaticSnippet"].includes(getEditor.technical_name);

        if (isStaticSnippet) {
            const StaticSnippet = registry.category("static_snippets").get("as_static_snippets");
            this.dialogService.add(StaticSnippets, {
                'snippet_content': StaticSnippet,
                'target': $(dropTarget),
                'snippet_builder': getEditor,
            });
            return;
        }

        $(dropTarget)
            .attr("data-snippet-name", getEditor.technical_name)
            .attr("data-records-ids", JSON.stringify([0]))
            .attr("data-modal", getEditor.model)
            .attr("data-design-edit", JSON.stringify(getEditor));

        if(this.editor.technical_name == "MegaMenuCategory" || this.editor.technical_name == "megamenu_category"){
            if(this.editor.extra_info.length != 0){
                $(dropTarget).attr("data-extra-info", JSON.stringify(this.subCategory.second_level_ids))
            }
        }
        const context = initDrop
            ? {
                'snippet': getEditor.technical_name,
                'record_ids': [0],
                'modal': getEditor.model,
                'design_editor': getEditor,
            }
            : {
                'snippet': this.editor.technical_name,
                'record_ids': this.state.record_ids,
                'modal': this.editor.model,
                'design_editor': this.editor,
            };

        const endpoint = this.props.snippet_type === "as_mega_menu" ? "/get_megamenu_snippet_template" : "/get_snippet_template";
        const response = await rpc(endpoint, context);

        if (response.record_ids == false) {
            this.dialogService.add(AlertDialog, {
                body: _t("Oops! This record could not be found."),
            });
            return;
        }

        Object.assign(this.editor, getEditor);
        this.state.record_ids = response.record_ids;
        this._get_style_layouts();

        const SnippetTechnicalNames = ['categories_products', 'brand_products', 'CategoryProduct', 'BrandProduct'];
        const isTabsSnippet = SnippetTechnicalNames.includes(this.editor.technical_name);

        $(dropTarget)
            .attr("data-snippet-name", getEditor.technical_name)
            .attr("data-records-ids", JSON.stringify(this.state.record_ids))
            .addClass("as-active-snippet-template");

        let $template = $(response['template']);
        if (isTabsSnippet) {
            $(dropTarget).find("div").first().replaceWith($template);
            $(dropTarget).find(".as_page_swiper").attr("id", "as_swiper_slider_as");
            if (this.editor.active_view === 'slider') {
                new Swiper("#as_swiper_slider_as", response.slider_config);
            }
            await this.get_snippet_data();
            this._sortable();
            $(dropTarget).find(".as_page_swiper").removeAttr("id");
        } else {
            $template.attr("id", "as_swiper_slider_as");
            $(dropTarget).find("div").first().replaceWith($template);
            if (this.editor.active_view === 'slider') {
                new Swiper("#as_swiper_slider_as", response.slider_config);
            }
            await this.get_snippet_data();
            this._sortable();
            $template.removeAttr("id");
        }
    }

    async getoptions(ev, collection){
        let $template = $(document.querySelector(".as-active-snippet-template"))
        let details = await rpc('/get_quick_record',{'mode':collection, 'model':this.editor.model})
        const records = details.map(detail => detail.id);
        this.state.record_ids = records
        await this.intialized_snippet($template, this.editor, false)
    }

    async _delete(ev){
        let rec_id = $(ev.target).parents(".as_data_info").attr("data-id");
        for (var i = 0; i < this.state.record_ids.length; i++) {
            if (this.state.record_ids[i] == rec_id) {
                this.state.record_ids.splice(i, 1);
            }
            if(this.state.record_info[i]['id'] == rec_id){
                this.state.record_info.splice(i, 1);
            }
        }
        $(ev.target).parents(".as_data_info").remove();
        if (this.state.record_ids.length > 0){
            let $template = $(document.querySelector(".as-active-snippet-template"))
            await this.intialized_snippet($template, this.editor, false)
        }
        else{
            let context = {
                'snippet': this.editor.technical_name,
                'record_ids': [],
                'modal': this.editor.model,
                'design_editor': this.editor,
            };
            let response = await rpc("/get_snippet_template", context);
            var $template =  $(response['template'])
            $(document.querySelector(".as-active-snippet-template")).find("div").first().replaceWith($template);
        }
    }
    _sortable(){
        let dataGroupId;
        var data = $(this.sortable_record.el);
        data.sortable({
            placeholder:"<li class='ui-sortable-placeholder'></li>",
            onDragStart: (params) => {
                params[0].classList.add('drag-start')
                dataGroupId = 1;
            },
            onDrop: (params) => {
                params[0].classList.remove('drag-start')
                this._update_record_sequence()
            },
        });
    }
    async _update_record_sequence(){
        let sort_record = $(document.querySelectorAll(".as_data_info"))
        let sort_record_list = [];
        for (const ele of sort_record) {
            sort_record_list.push($(ele).data("id"));
        }
        this.state.record_ids = sort_record_list;
        let $template = $(document.querySelector(".as-active-snippet-template"))
        await this.intialized_snippet($template, this.editor,  false)
    }
    // Save Snippets
    _save(){
        const snippet_content = this.snippet_preview.el
        var target = this.props.target.$target

        $(snippet_content).find(".as_col").each(function() {
            let SnippetConfig = JSON.parse($(this).attr("data-design-edit"))
            if($(this).attr("data-snippet-name") != "static_snippets")
            {
                $(this).empty().append("<div class='text-center'> <h3>"+SnippetConfig.name+"</h3> </div>");
            }
            else{
                $(this).find(".as-sb-drop-action").empty();
            }

        });
        $(target).empty().append(snippet_content);
        this.props.close();
    }

    // Design & Edit
    async _change_active_view(ev){
        this.editor.active_view = $(ev.target).val();
        if($(ev.target).val() == "grid"){
            this.editor.auto_slider = false;
            this.editor.template_id = this.editor.default_gtemplate_id
        }else{
            this.editor.template_id = this.editor.default_stemplate_id
        }

        let $template = $(document.querySelector(".as-active-snippet-template"))
        await this.intialized_snippet($template, this.editor,  false)
    }

    async _change_record_limit(ev){
        this.editor.record_limit = $(ev.target).val();
        let $template = $(document.querySelector(".as-active-snippet-template"))
        await this.intialized_snippet($template, this.editor,  false)
    }

    async _change_slider_time(ev){
        this.editor.slider_time = $(ev.target).val();
        let $template = $(document.querySelector(".as-active-snippet-template"))
        await this.intialized_snippet($template, this.editor,  false)
    }
    async _change_col_item(ev){
        if(this.props.snippet_type == "as_mega_menu"){
            this.editor.col_item = $(ev.target).val();
        }
        else{
            let screen_view = $(ev.target).attr("data-view-type")
            if(screen_view == "desk"){
                this.editor.default_col_desk = $(ev.target).val();
            }else if(screen_view == "mob"){
                this.editor.default_col_mob = $(ev.target).val();
            }
        }

        let $template = $(document.querySelector(".as-active-snippet-template"))
        await this.intialized_snippet($template, this.editor,  false)
    }
    async _change_grid_style(ev){
        this.editor.grid_style = $(ev.target).val();
        let option = "[value='"+ $(ev.target).val() +"']";
        this.editor.template_id = $(ev.target).find(option).attr("data-template");
        let $template = $(document.querySelector(".as-active-snippet-template"))
        await this.intialized_snippet($template, this.editor,  false)
    }
    async _change_slider_style(ev){
        this.editor.slider_style = $(ev.target).val();
        let option = "[value='"+ $(ev.target).val() +"']";
        this.editor.template_id = $(ev.target).find(option).attr("data-template");
        let $template = $(document.querySelector(".as-active-snippet-template"))
        await this.intialized_snippet($template, this.editor,  false)
    }
    async _change_pagination(ev){
        this.editor.pagination = $(ev.target).val();
        let $template = $(document.querySelector(".as-active-snippet-template"))
        await this.intialized_snippet($template, this.editor,  false)
    }
    async _change_quick_option(ev){
        let quick_option = $(ev.target).data("target");

        if(quick_option == "allow_add_to_cart"){
            this.editor.allow_add_to_cart = $(ev.target).prop("checked");
        }else if(quick_option == "allow_quick_view"){
            this.editor.allow_quick_view = $(ev.target).prop("checked");
        }else if(quick_option == "allow_compare"){
            this.editor.allow_compare = $(ev.target).prop("checked");
        }else if(quick_option == "allow_wishlist"){
            this.editor.allow_wishlist = $(ev.target).prop("checked");
        }else if(quick_option == "allow_rating"){
            this.editor.allow_rating = $(ev.target).prop("checked");
        }else if(quick_option == "allow_label"){
            this.editor.allow_label = $(ev.target).prop("checked");
        }else if(quick_option == "allow_hover_image"){
            this.editor.allow_hover_image = $(ev.target).prop("checked");
        }else if(quick_option == "allow_stock_info"){
            this.editor.allow_stock_info = $(ev.target).prop("checked");
        }else if(quick_option == "allow_offer_time"){
            this.editor.allow_offer_time = $(ev.target).prop("checked");
        }else if(quick_option == "allow_brand_info"){
            this.editor.allow_brand_info = $(ev.target).prop("checked");
        }else if(quick_option == "allow_color_variant"){
            this.editor.allow_color_variant = $(ev.target).prop("checked");
        }else if(quick_option == "loop"){
            this.editor.loop = $(ev.target).prop("checked");
        }else if(quick_option == "tabs"){
            this.editor.tabs = $(ev.target).prop("checked");
        }else if(quick_option == "allow_link"){
            this.editor.allow_link = $(ev.target).prop("checked");
        }
        let $template = $(document.querySelector(".as-active-snippet-template"))
        await this.intialized_snippet($template, this.editor,  false)
    }
    _change_static_snippets(){
        const StaticSnippet = registry.category("static_snippets").get("as_static_snippets");
        let $template = $(document.querySelector(".as-active-snippet-template"))
        this.dialogService.add(StaticSnippets, {
            'snippet_content':StaticSnippet,
            'target':$($template),
            'snippet_builder':this.editor,
        });
    }
    async _change_auto_slider(ev){
        if(this.editor.auto_slider){
            this.editor.auto_slider = false;
        }else{
            this.editor.auto_slider = true;
        }
        let $template = $(document.querySelector(".as-active-snippet-template"))
        await this.intialized_snippet($template, this.editor,  false)
    }

    async _init_sub_cat_data(parent_id, type_ids){

        let second_level = this.subCategory.second_level;
        let second_level_ids = this.subCategory.second_level_ids;

        let sl_info_update = false;
        let sl_ids_update = false;
        let details = [];
        if(type_ids != []){
            details = await rpc('/get_records_details',{'record_ids':type_ids, 'model':"product.public.category"});
        }
        for (const sl_info of second_level) {
            if(parent_id  == sl_info['parent']){
                sl_info['childs'] = details;
                sl_info_update = true;
            }
        }

        for (const sl_ids of second_level_ids) {
           if(sl_ids['parent'] == parent_id){
                sl_ids['childs'] = type_ids;
                sl_ids_update = true;
            }
        }

        if(!sl_info_update){
            second_level.push({'parent':parent_id,'childs':details});
        }
        if(!sl_ids_update){
            second_level_ids.push({'parent':parent_id,'childs':type_ids});
        }
        this.editor.extra_info = this.subCategory.second_level_ids
        let $template = $(document.querySelector(".as-active-snippet-template"))
        await this.intialized_snippet($template, this.editor,  false)

    }

    select_sub_category(ev){

        let id = $(ev.target).data("id");
        let pre_select_cats = $(ev.target).attr("data-sub-cat");
        this.dialogService.add(SubCategory, {
            parent_id: id,
            pre_selected_vals:pre_select_cats,
            pre_selected_data:[],
            _submit_second_category: async(vals)=>{
                $(ev.target).attr("data-sub-cat",vals);
                if(vals != "" && vals!= undefined){
                    let type_ids = vals.split(",");
                    this._init_sub_cat_data(id, type_ids)

                }else{
                    this._init_sub_cat_data(id, [])
                }
            }


        });
    }
    get_sub_category(parent_id){

        if(this.editor.extra_info){
            for (const cat of this.editor.extra_info) {
                if(cat['parent'] == parent_id){
                    return [cat['childs'].toString(), cat['childs'].length]
                }
            }
        }

        return ["",0]
    }

}
