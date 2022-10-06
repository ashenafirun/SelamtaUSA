/** @odoo-module **/

import publicWidget from "web.public.widget";
import "website_sale.website_sale";
import ajax from "web.ajax";
import session from "web.session";
import { qweb as QWeb } from "web.core";

const loadXml = async () => {
    return ajax.loadXML('/out_of_stock_notification/static/src/xml/product_availability.xml', QWeb);
};

publicWidget.registry.WebsiteSale.include({

    _onChangeCombination: async function (ev, $parent, combination) {
        this._super(...arguments).then(() => {
            loadXml().then(() => {
                if($('#stock_wishlist_message').length) { $('#stock_wishlist_message').remove() }
                if ($('.availability_messages').length && !session.is_website_user) {
                    var $elem = $(QWeb.render('out_of_stock_notification.product_availability', combination))
                    $('.availability_messages').append($elem);

                    $elem.find('input').on('click', _.debounce((e) => {
                        this._rpc({
                            route: `/shop/back/stock/notify`,
                            params: {
                                notify: $(e.currentTarget).is(':checked'),
                                product_id: $(e.currentTarget).data('productId'),
                            }
                        });
                    }, 500));
                }
            });
        });
    },
});
