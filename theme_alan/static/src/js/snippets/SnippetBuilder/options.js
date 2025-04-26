/** @odoo-module **/

import { SnippetBuilder } from "./SnippetBuilder"
import { registry } from "@web/core/registry";
import options from "@web_editor/js/editor/snippets.options";

options.registry.SnippetBuilderOption = options.Class.extend({

    events:{
        'click .as_snippet_open_preview':'_openSnippetConfigure',
    },

    init() {
        this._super(...arguments);
        this.dialog = this.bindService("dialog");
        this.$target.on("click", () => this._openSnippetConfigure());
    },

    _openSnippetConfigure() {
        const snippet_type = this.$target.attr("data-as-snippet");
        const DynamicSnippetLists = registry.category("snippet_builder").get("as_dynamic_snippets");
        const MegamenuSnippetLists = registry.category("snippet_builder").get("as_megamenu_snippets");
        const SnippetLists = snippet_type === "as_mega_menu" ? MegamenuSnippetLists : DynamicSnippetLists;
        let config_data = $(this.$target).find(".as-snippet-preview");
        const is_static = this.$target.hasClass("as_static_menu");
        if(config_data.length == 0 || config_data.find(".as_col").length == 0){
            config_data = undefined
        }
        if (!is_static) {
            this.dialog.add(SnippetBuilder, {
                snippets: SnippetLists,
                target: this,
                config_data,
                snippet_type,
                confirm: () => resolve(true),
                cancel: () => resolve(false),
            });
        }
    },

    onBuilt() {
        const SnippetLists = registry.category("snippet_builder").get("as_dynamic_snippets");
        const snippet_type = this.$target.attr("data-as-snippet");
        this.dialog.add(SnippetBuilder, {
            snippets: SnippetLists,
            target: this,
            snippet_type,
            confirm: () => resolve(true),
            cancel: () => resolve(false),
        });
    }
})
