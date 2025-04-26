/** @odoo-module **/

import { Component, useRef, useState, onMounted} from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

export class FrameBuilder extends Component {
    static template = "theme_alan.frame_builder"
    setup() {
        this.row_class = Array.from({ length: 12 }, (_, i) => `col-${i + 1}`).join(' ');
        this.state = useState({
            'enable_resize':false,
            'active_row':false,
            'resize_position':false,
        })
        this.row = useRef("main_row");

        onMounted(async () => {
            const config_data = this.props.snippetBuilder.props.config_data;
            const editor_container = `<div class="as-sb-drop-action">${$(".as-snippet-preview").find(".as-sb-drop-action").html()}</div>`;
            const isMegaMenu = this.props.snippetBuilder.props.snippet_type === "as_mega_menu";
            const SnippetTechnicalNames = ['categories_products', 'brand_products', 'CategoryProduct', 'BrandProduct'];

            if (config_data) {
                $(".as-snippet-preview").empty().append(config_data.html());

                const frames = $(".as_col");
                const framePromises = Array.from(frames).map(async (frame) => {
                    const $frame = $(frame);
                    const SnippetName = $frame.attr("data-snippet-name");

                    if (["static_snippets", "StaticSnippet"].includes(SnippetName)) {
                        $frame.append(editor_container);
                        return;
                    }

                    const context = {
                        snippet: SnippetName,
                        record_ids: JSON.parse($frame.attr("data-records-ids")),
                        modal: $frame.attr("data-modal"),
                        design_editor: JSON.parse($frame.attr("data-design-edit")),
                    };

                    const endpoint = isMegaMenu ? "/get_megamenu_snippet_template" : "/get_snippet_template";
                    const response = await rpc(endpoint, context);

                    const isTabsSnippet = SnippetTechnicalNames.includes(SnippetName);

                    if(isTabsSnippet){
                        var $template =  $(response['template'])
                        $frame.empty().append($template );
                        $frame.append(editor_container)
                        $frame.find(".as_page_swiper").attr("id", "as_swiper_slider_as");
                        if(JSON.parse($frame.attr("data-design-edit")).active_view == 'slider'){
                            new Swiper("#as_swiper_slider_as",response.slider_config)
                        }

                    }
                    else{
                        var $template =  $(response['template']).attr("id","as_swiper_slider_as");
                        $frame.empty().append($template );
                        $frame.append(editor_container)
                        if(JSON.parse($frame.attr("data-design-edit")).active_view == 'slider'){
                            new Swiper("#as_swiper_slider_as",response.slider_config)
                        }
                        $template.removeAttr("id");
                    }
                });

                await Promise.all(framePromises);
                this._bindRowEvents(frames);
            }
        });


    }
    AddFrame(){
        $(".as-snippet-drop-container").removeClass("d-none")
        $(".as-build-frame").addClass("d-none")
    }
    async handleclick(e){
        let target = $(e.target)
        document.querySelectorAll('.as_col').forEach(function(element) {
            element.classList.remove("as-active-snippet-template");
        });

        if($(e.target).parents(".as_col").length > 0){
            $(e.target).parents(".as_col").addClass("as-active-snippet-template")
            target = $(e.target).parents(".as_col")
        }
        else{
            $(e.target).addClass("as-active-snippet-template")
        }
        if (this.props.snippetBuilder) {
            this.props.snippetBuilder.handleclick(target);
        }
    }
    resize(e){
        let row = $(e.target).attr("data-row");
        $(e.target).parents(".as_col").removeClass(this.row_class).addClass(row);
    }
    add_col(e){
        const $originalCol = $(e.target).parents(".as_col");
        const $newCol = $originalCol.clone();
        // $newCol.attr("data-snippet-id", Date.now())
        $originalCol.after($newCol);
        this._bindRowEvents($newCol);
    }
    delete_col(e){
        if($(".as_col").length == 1){
            $(".as-build-frame").removeClass("d-none")
            $(e.target).parents(".as_col").addClass("d-none")
            let frame_container = `<div class="container"></div>`
            $(e.target).parents(".as_col").find("div").first().replaceWith(frame_container)
            $(e.target).parents(".as_col").removeAttr("data-snippet-name");
            $(e.target).parents(".as_col").removeAttr("data-records-ids");
            $(e.target).parents(".as_col").removeAttr("data-modal");
            $(e.target).parents(".as_col").removeAttr("data-design-edit");
            this.props.snippetBuilder.editor = {
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
                "allow_link":false
            }
            this.props.snippetBuilder.state.record_ids = []
            this.props.snippetBuilder.state.record_info = []
        }
        else{
            $(e.target).parents(".as_col").remove();
        }

    }
    _bindRowEvents($col){
        $col.find('.as_col_select').on('click', this.resize.bind(this));
        $col.find('.add_col').on('click', this.add_col.bind(this));
        $col.find('.delete_col').on('click', this.delete_col.bind(this));
        $col.find('.pos_col').on('click', this.change_col_pos.bind(this));
        $col.on('click', this.handleclick.bind(this));
    }
    change_col_pos(e){
        let direction = $(e.target).attr("data-cp");
        const $originalCol = $(e.target).parents(".as_col");
        if(direction == "right"){
            let $next = $originalCol.next(".as_col");
            $originalCol.insertAfter($next);
        }else{
            let $pre = $originalCol.prev(".as_col")
            $originalCol.insertBefore($pre);
        }
    }
}