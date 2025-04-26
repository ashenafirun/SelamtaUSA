/** @odoo-module **/

import { registry } from '@web/core/registry';

const SnippetRegistries = registry.category("snippet_builder");
const WebsiteBuilderRegistries = registry.category("website_builder");
const StaticSnippetRegistries = registry.category("static_snippets");

const products = {
    "name": "Products",
    "technical_name": "products",
    "design": true,
    "selection": true,
    "model": "product.template",
    "view": ["slider", "grid"],
    "active_view": "slider",
    "loop": true,
    "auto_slider": true,
    "slider_time": 6,
    "pagination": "none",
    "default_col_mob": 2,
    'default_col_desk':"5",
    "grid_style":"as-grid-1",
    "slider_style":"as-slider-1",
    "grid_layout_style": "s_product_grid",
    "slider_layout_style": "s_product_slider",
    "template_id": "theme_alan.s_product_slider",
    'default_stemplate_id':'theme_alan.s_product_slider',
    'default_gtemplate_id':'theme_alan.s_product_grid',
    "allow_add_to_cart": true,
    "allow_quick_view": true,
    "allow_compare": false,
    "allow_wishlist": true,
    "allow_rating": false,
    "allow_label": true,
    "allow_hover_image": false,
    "allow_stock_info": false,
    "allow_offer_time": false,
    "allow_brand_info": false,
    "allow_color_variant": true,
    "quick_selection": [{
                    'latest_product': 'Newest Product',
                    'best_seller': 'Best Seller Product',
                    'top_related': 'Top Related Product',
                    'random': 'Random product'}],
}
const category_products = {
    "name": "Category Products",
    "technical_name": "categories_products",
    "design": true,
    "selection": true,
    "model": "product.public.category",
    "view": ["slider", "grid"],
    "active_view": "slider",
    "loop": true,
    "auto_slider": true,
    "slider_time": 6,
    "pagination": "none",
    "default_col_mob": 2,
    'default_col_desk':"5",
    "grid_style":"as-tab-grid-1",
    "slider_style":"as-tab-slider-1",
    "grid_layout_style": "s_category_product_grid",
    "slider_layout_style": "s_category_product_slider",
    "style":"as-category-product-1",
    "template_id": "theme_alan.s_category_product_slider",
    'default_stemplate_id':'theme_alan.s_category_product_slider',
    'default_gtemplate_id':'theme_alan.s_category_product_grid',
    "allow_add_to_cart": true,
    "allow_quick_view": true,
    "allow_compare": false,
    "allow_wishlist": true,
    "allow_rating": false,
    "allow_label": true,
    "allow_hover_image": false,
    "allow_stock_info": false,
    "allow_offer_time": false,
    "allow_brand_info": false,
    "allow_color_variant": true,
    "record_limit": 10,
    "quick_selection": [{
                    'parent_category': 'Top Level Category',
                    'a_to_z': 'A to Z',
                    'z_to_a': 'Z to A',
                    'random': 'Random Category'}]
}
const brands_products = {
    "name": "Brand Products",
    "technical_name": "brand_products",
    "design": true,
    "selection": true,
    "model": "as.product.brand",
    "view": ["slider", "grid"],
    "active_view": "slider",
    "loop": true,
    "auto_slider": true,
    "slider_time": 6,
    "pagination": "none",
    "default_col_mob": 2,
    'default_col_desk':"5",
    'grid_style':'as-tab-grid-1',
    'slider_style':'as-tab-slider-1',
    "grid_layout_style": "s_brand_product_grid",
    "slider_layout_style": "s_brand_product_slider",
    "template_id": "theme_alan.s_brand_product_slider",
    'default_stemplate_id':'theme_alan.s_brand_product_slider',
    'default_gtemplate_id':'theme_alan.s_brand_product_grid',
    "allow_add_to_cart": true,
    "allow_quick_view": true,
    "allow_compare": false,
    "allow_wishlist": true,
    "allow_rating": false,
    "allow_label": true,
    "allow_hover_image": false,
    "allow_stock_info": false,
    "allow_offer_time": false,
    "allow_brand_info": false,
    "allow_color_variant": true,
    "record_limit": 10,
    "quick_selection": [{
                    'a_to_z': 'A to Z',
                    'z_to_a': 'Z to A',
                    'random': 'Random Brand'}]
}

const category = {
    "name": "Categories",
    "design": true,
    "technical_name": "categories",
    "selection": true,
    "model": "product.public.category",
    "view": ["slider", "grid"],
    "active_view": "slider",
    "loop": true,
    "auto_slider": true,
    "slider_time": 6,
    "default_col_mob": 2,
    'default_col_desk':"5",
    "pagination": "none",
    'grid_style':'as-grid-1',
    'slider_style':'as-slider-1',
    "grid_layout_style": "s_category_grid",
    "slider_layout_style": "s_category_slider",
    "template_id": "theme_alan.s_category_slider",
    'default_stemplate_id':'theme_alan.s_category_slider',
    'default_gtemplate_id':'theme_alan.s_category_grid',
    "quick_selection": [{
                    'parent_category': 'Top Level Category',
                    'a_to_z': 'A to Z',
                    'z_to_a': 'Z to A',
                    'random': 'Random Category'}]
}
const brand = {
    "name": "Brands",
    "design": true,
    "technical_name": "brands",
    "selection": true,
    "model": "as.product.brand",
    "view": ["slider", "grid"],
    "active_view": "slider",
    "loop": true,
    "auto_slider": true,
    "slider_time": 6,
    "default_col_mob": 2,
    'default_col_desk':"5",
    "pagination": "none",
    'grid_style':'as-grid-1',
    'slider_style':'as-slider-1',
    "grid_layout_style": "s_brand_grid",
    "slider_layout_style": "s_brand_slider",
    "template_id": "theme_alan.s_brand_slider",
    'default_stemplate_id':'theme_alan.s_brand_slider',
    'default_gtemplate_id':'theme_alan.s_brand_grid',
    'allow_link':true,
    "quick_selection": [{
                    'a_to_z': 'A to Z',
                    'z_to_a': 'Z to A',
                    'random': 'Random Brand'}]
}
const product_banner = {
    "name": "Product Banner",
    "technical_name": "product_banner",
    "design": true,
    "selection": true,
    "model": "product.template",
    "view": ["slider", "grid"],
    "active_view": "slider",
    "loop": true,
    "auto_slider": true,
    "slider_time": 6,
    "pagination": "none",
    "default_col_mob": 1,
    'default_col_desk':"1",
    "grid_style":"as-grid-1",
    "slider_style":"as-slider-1",
    "grid_layout_style": "s_product_banner_grid",
    "slider_layout_style": "s_product_banner_slider",
    "template_id": "theme_alan.s_product_banner_slider",
    'default_stemplate_id':'theme_alan.s_product_banner_slider',
    'default_gtemplate_id':'theme_alan.s_product_banner_grid',
    "allow_add_to_cart": true,
    "allow_quick_view": true,
    "allow_compare": false,
    "allow_wishlist": true,
    "allow_rating": false,
    "allow_label": true,
    "allow_hover_image": false,
    "allow_stock_info": false,
    "allow_offer_time": false,
    "allow_brand_info": false,
    "allow_color_variant": true,
    "quick_selection": [{
                    'latest_product': 'Newest Product',
                    'best_seller': 'Best Seller Product',
                    'top_related': 'Top Related Product',
                    'random': 'Random product'}]
}
const blog = {
    "name": "Blogs",
    "technical_name": "blogs",
    "design": true,
    "selection": true,
    "model": "blog.post",
    "view": ["slider", "grid"],
    "active_view": "slider",
    "loop": true,
    "auto_slider": true,
    "slider_time": 6,
    "pagination": "none",
    "default_col_mob": 2,
    'default_col_desk':"5",
    "style":"as-blog-1",
    "grid_style":"as-grid-1",
    "slider_style":"as-slider-1",
    "grid_layout_style": "s_blog_grid",
    "slider_layout_style": "s_blog_slider",
    "template_id": "theme_alan.s_blog_slider",
    'default_stemplate_id':'theme_alan.s_blog_slider',
    'default_gtemplate_id':'theme_alan.s_blog_grid',
    "quick_selection": [{
                    'a_to_z': 'A to Z',
                    'z_to_a': 'Z to A',
                    'random': 'Random Blog'}]
}

const static_snippets =  { "name":"Structure Blocks",
                        "technical_name":"static_snippets",
                        "design":false,
                        "selection":false,
                        "template_id": false,
                    }

SnippetRegistries.add("as_dynamic_snippets",  [
            products,
            category_products,
            brands_products,
            category,
            brand,
            product_banner,
            blog,
            static_snippets,
        ] );

let as_static_snippets = [
    {
        'list':[
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-1.png',
                'name':'Snippet 1',
                'temp_id':'slider_temp_1'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-2.png',
                'name':'Snippet 2',
                'temp_id':'slider_temp_2'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-3.png',
                'name':'Snippet 3',
                'temp_id':'slider_temp_3'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-4.png',
                'name':'Snippet 4',
                'temp_id':'slider_temp_4'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-5.jpg',
                'name':'Snippet 5',
                'temp_id':'slider_temp_5'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-6.png',
                'name':'Snippet 6',
                'temp_id':'slider_temp_6'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-7.jpg',
                'name':'Snippet 7',
                'temp_id':'slider_temp_7'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-8.png',
                'name':'Snippet 8',
                'temp_id':'slider_temp_8'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-9.png',
                'name':'Snippet 9',
                'temp_id':'slider_temp_9'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-10.png',
                'name':'Snippet 10',
                'temp_id':'slider_temp_10'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-11.png',
                'name':'Snippet 11',
                'temp_id':'slider_temp_11'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-12.png',
                'name':'Snippet 12',
                'temp_id':'slider_temp_12'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-13.png',
                'name':'Snippet 13',
                'temp_id':'slider_temp_13'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-14.png',
                'name':'Snippet 14',
                'temp_id':'slider_temp_14'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-15.jpg',
                'name':'Snippet 15',
                'temp_id':'slider_temp_15'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-16.png',
                'name':'Snippet 16',
                'temp_id':'slider_temp_16'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-17.jpg',
                'name':'Snippet 17',
                'temp_id':'slider_temp_17'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-18.png',
                'name':'Snippet 18',
                'temp_id':'slider_temp_18'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-19.png',
                'name':'Snippet 19',
                'temp_id':'slider_temp_19'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-20.png',
                'name':'Snippet 20',
                'temp_id':'slider_temp_20'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-21.png',
                'name':'Snippet 21',
                'temp_id':'slider_temp_21'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-22.jpg',
                'name':'Snippet 22',
                'temp_id':'slider_temp_22'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-23.png',
                'name':'Snippet 23',
                'temp_id':'slider_temp_23'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-24.png',
                'name':'Snippet 24',
                'temp_id':'slider_temp_24'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-25.png',
                'name':'Snippet 25',
                'temp_id':'slider_temp_25'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-26.png',
                'name':'Snippet 26',
                'temp_id':'slider_temp_26'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-27.png',
                'name':'Snippet 27',
                'temp_id':'slider_temp_27'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-28.png',
                'name':'Snippet 28',
                'temp_id':'slider_temp_28'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-29.png',
                'name':'Snippet 29',
                'temp_id':'slider_temp_29'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-30.png',
                'name':'Snippet 30',
                'temp_id':'slider_temp_30'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-31.png',
                'name':'Snippet 31',
                'temp_id':'slider_temp_31'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-32.png',
                'name':'Snippet 32',
                'temp_id':'slider_temp_32'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-33.png',
                'name':'Snippet 33',
                'temp_id':'slider_temp_33'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-34.png',
                'name':'Snippet 34',
                'temp_id':'slider_temp_34'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-35.png',
                'name':'Snippet 35',
                'temp_id':'slider_temp_35'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-36.png',
                'name':'Snippet 36',
                'temp_id':'slider_temp_36'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-37.png',
                'name':'Snippet 37',
                'temp_id':'slider_temp_37'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-38.png',
                'name':'Snippet 38',
                'temp_id':'slider_temp_38'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-39.png',
                'name':'Snippet 39',
                'temp_id':'slider_temp_39'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-40.png',
                'name':'Snippet 40',
                'temp_id':'slider_temp_40'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-41.png',
                'name':'Snippet 41',
                'temp_id':'slider_temp_41'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-42.png',
                'name':'Snippet 42',
                'temp_id':'slider_temp_42'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-43.png',
                'name':'Snippet 43',
                'temp_id':'slider_temp_43'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-44.png',
                'name':'Snippet 44',
                'temp_id':'slider_temp_44'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-45.png',
                'name':'Snippet 45',
                'temp_id':'slider_temp_45'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-46.png',
                'name':'Snippet 46',
                'temp_id':'slider_temp_46'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-47.png',
                'name':'Snippet 47',
                'temp_id':'slider_temp_47'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-48.png',
                'name':'Snippet 48',
                'temp_id':'slider_temp_48'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-49.png',
                'name':'Snippet 49',
                'temp_id':'slider_temp_49'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-50.png',
                'name':'Snippet 50',
                'temp_id':'slider_temp_50'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-51.png',
                'name':'Snippet 51',
                'temp_id':'slider_temp_51'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-52.png',
                'name':'Snippet 52',
                'temp_id':'slider_temp_52'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-53.png',
                'name':'Snippet 53',
                'temp_id':'slider_temp_53'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-54.png',
                'name':'Snippet 54',
                'temp_id':'slider_temp_54'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-55.png',
                'name':'Title Style 1',
                'temp_id':'banner_temp_1'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-56.png',
                'name':'Title Style 2',
                'temp_id':'banner_temp_2'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-57.png',
                'name':'Title Style 3',
                'temp_id':'banner_temp_3'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-58.png',
                'name':'Title Style 4',
                'temp_id':'banner_temp_4'
            },
            {
                'img_url':'/theme_alan/static/src/img/snippets/dynamic_snippets/dy_snippet-59.png',
                'name':'Title Style 5',
                'temp_id':'banner_temp_5'
            },
        ]
    },

]

StaticSnippetRegistries.add("as_static_snippets", as_static_snippets);

const  snippet_categories = {
    "e_slider": "Slider",
    "e_banner": "Banner",
    "e_about": "About",
    "e_title_style": "Title Style",
    "e_cta": "Call To Action",
    "e_category": "Category",
    "e_our_client": "Our Client",
    "e_collection": "Collection",
    "e_contact_us": "Contact Us",
    "e_features": "Features",
    "e_our_team": "Our Team",
    "e_portfolio": "Portfolio",
    "e_price_table": "Price Table",
    "e_promotion": "Promotion",
    "e_services": "Services",
    "e_shop_banner": "Shop Banner",
    "e_testimonial": "Testimonial",
    "e_video_popup": "Video Popup",
    "e_subscribe_newsletter": "Subscribe Newsletter"
};

WebsiteBuilderRegistries.add("as_snippet_categories", snippet_categories);


const megamenu_products = {
    "name": "Menu Products",
    "technical_name": "megamenu_products",
    "design": true,
    "selection": true,
    "model": "product.template",
    "view": ["slider", "grid"],
    "active_view": "slider",
    "loop": true,
    "auto_slider": true,
    "slider_time": 6,
    "col_item":4,
    "grid_style":"as-mm-product-snippet-1",
    "slider_style":"as-mm-product-snippet-1",
    "grid_layout_style": "m_product_grid",
    "slider_layout_style": "m_product_slider",
    "template_id": "theme_alan.m_product_slider",
    'default_stemplate_id':'theme_alan.m_product_slider',
    'default_gtemplate_id':'theme_alan.m_product_grid',
    "quick_selection": [{
                    'latest_product': 'Newest Product',
                    'best_seller': 'Best Seller Product',
                    'top_related': 'Top Related Product',
                    'random': 'Random product'}],
}

const megamenu_category = {
    "name": "Menu Category",
    "technical_name": "megamenu_category",
    "design": true,
    "selection": true,
    "model": "product.public.category",
    "view": ["slider", "grid"],
    "active_view": "slider",
    "loop": true,
    "auto_slider": true,
    "slider_time": 6,
    "col_item":4,
    "grid_style":"as-mm-category-grid-1",
    "slider_style":"as-mm-category-slider-1",
    "grid_layout_style": "m_category_grid",
    "slider_layout_style": "m_category_slider",
    "template_id": "theme_alan.m_category_slider",
    'default_stemplate_id':'theme_alan.m_category_slider',
    'default_gtemplate_id':'theme_alan.m_category_grid',
    'extra_info':[],
    "quick_selection": [{
        'parent_category': 'Top Level Category',
        'a_to_z': 'A to Z',
        'z_to_a': 'Z to A',
        'random': 'Random Category'}]
}

const megamenu_brand = {
    "name": "Menu Brand",
    "technical_name": "megamenu_brand",
    "design": true,
    "selection": true,
    "model": "as.product.brand",
    "view": ["slider", "grid"],
    "active_view": "slider",
    "loop": true,
    "auto_slider": true,
    "slider_time": 6,
    "pagination": "none",
    "col_item":4,
    'allow_link':true,
    "grid_style":"as-mm-brand-snippet-1",
    "slider_style":"as-mm-brand-snippet-1",
    "grid_layout_style": "m_brand_grid",
    "slider_layout_style": "m_brand_slider",
    "template_id": "theme_alan.m_brand_slider",
    'default_stemplate_id':'theme_alan.m_brand_slider',
    'default_gtemplate_id':'theme_alan.m_brand_grid',
    "quick_selection": [{
                    'a_to_z': 'A to Z',
                    'z_to_a': 'Z to A',
                    'random': 'Random Brand'}]


}


SnippetRegistries.add("as_megamenu_snippets",  [
    megamenu_products,
    megamenu_category,
    megamenu_brand,
    static_snippets
] );
