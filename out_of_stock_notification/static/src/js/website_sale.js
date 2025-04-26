/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import WebsiteSale from '@website_sale/js/website_sale';
import { renderToElement } from "@web/core/utils/render";
import { renderToFragment } from "@web/core/utils/render";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { debounce, Deferred } from "@bus/workers/websocket_worker_utils";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.WebsiteSale.include({

    _onChangeCombination: async function (ev, $parent, combination) {
        this._super(...arguments);
        if($('#stock_wishlist_message').length) { $('#stock_wishlist_message').remove() }
        if ($('.availability_messages').length && !session.is_website_user) {
            var $elem = $(renderToFragment('out_of_stock_notification.product_availability', combination) || '')
            $('.availability_messages').append($elem);
            $('#back_to_stock').on('click', debounce((e) => {
                rpc("/shop/back/stock/notify", {
                        notify: $(e.currentTarget).is(':checked'),
                        product_id: $(e.currentTarget).data('productId'),
                    });
            }, 500));
        }
    },
});
