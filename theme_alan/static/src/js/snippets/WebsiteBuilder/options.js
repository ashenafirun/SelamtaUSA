/** @odoo-module **/

import { registry } from "@web/core/registry";
import { WebsiteBuilder } from "./WebsiteBuilder"
import { _t } from '@web/core/l10n/translation';
import options from "@web_editor/js/editor/snippets.options";

options.registry.alan_website_builder = options.Class.extend({
    events:{'click':'_changeCollection' },
    init() {
        this._super(...arguments);
        this.dialog = this.bindService("dialog");
    },
    _changeCollection:function(){
        this.select_snippet('click','true');
    },
    select_snippet: function() {
        const SnippetTabs = registry.category("website_builder").get("as_snippet_categories");
        this.id = this.$target.attr('id');

        this.dialog.add(WebsiteBuilder,{
            'tabs':SnippetTabs,
            'target':this,
            confirm: () => resolve(true),
            cancel: () => resolve(false),

        })
    },
    onBuilt: function () {

        this._super();
        this.select_snippet('click', 'true');
    },
});
