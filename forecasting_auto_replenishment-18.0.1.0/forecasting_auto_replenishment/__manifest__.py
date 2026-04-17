# -*- coding: utf-8 -*-pack
{  # App information
    'name': 'Advanced Demand Forecasting & Smart Inventory Replenishment with Overstock & Deadstock Analysis for Odoo | Product Forcasting Report | Deadstock Report | Overstock Report | Slow Moving Products | Auto Generate Replenishment | Inventory Planning | Replenishment Planning | Demand Planning | Future Demand Prediction | Auto Replenishment',
    'category': 'Sales',
    'version': '18.0.1.0',
    'sequence': 1,
    'summary': """Our Advanced Demand Forecasting and Automated Stock Replenishment module offers a sophisticated approach to forecast product quantities and inventory management by replacing static reordering rules with dynamic, data-driven planning. 
    By analyzing historical consumption trends and applying forecasting methods as per your configuration, the system accurately predicts future needs while accounting for seasonality adjustments and specific order cycles. 
    It ensures optimal stock levels by factoring in critical variables such as safety stock, lead times, and stock limits, effectively preventing both costly shortages and inefficient overstocking.
    The module streamlines complex logistics through multi-warehouse priority logic, automatically determining whether to fulfill needs via internal transfers or new purchase orders based on your specific source warehouse constraints. 
    This automation is supported by high-level control features, including detailed logs and inventory reports that provide full visibility into every system action. 
    By integrating these advanced planning tools directly into Odoo, your business can maintain a leaner inventory, optimize cash flow, and ensure that procurement always aligns with real-world demand trends.
    
    Predicts Future Stock
    Inventory Management
    Auto create PO based on Requirement
    Internal Warehsue Transfer based on Forecast
    Forecast based on seasonality adjustments
    Forecast quantity by Product Category
    Forecast quantity by Product Template
    Forecast quantity by Vendor Products
     
    
    Prévisions intelligentes de la demande et réapprovisionnement automatique pour Odoo | Prédiction de la demande future | Prévisions des stocks | Réapprovisionnement automatique |
    Prévision des stocks futurs | Gestion des stocks | Création automatique de bons de commande (PO) selon les besoins | Transferts internes entre entrepôts basés sur les prévisions | 
    Prévisions basées sur les ajustements saisonniers | Prévision des quantités par catégorie de produits | Prévision des quantités par modèle de produit | Prévision des quantités par produits fournisseurs | 
    
    Intelligente Bedarfsprognose & automatische Bestandsauffüllung für Odoo | Vorhersage des zukünftigen Bedarfs | Lagerbestandsprognose | Automatische Nachbevorratung |
    Vorhersage zukünftiger Bestände | Bestandsverwaltung | Automatische Bestellung (PO) nach Bedarf | Interne Lagerumbuchungen basierend auf Prognosen | Prognosen basierend auf Saisonanpassungen | 
    Mengenprognose nach Produktkategorie | Mengenprognose nach Produktvorlage | Mengenprognose nach Lieferantenprodukten |
    
    Previsión inteligente de la demanda y reabastecimiento automático para Odoo | Predicción de la demanda futura | Previsión de inventarios | Reabastecimiento automático |
    Predicción de existencias futuras | Gestión de inventario | Creación automática de pedidos (PO) según requerimientos | Transferencia interna entre almacenes basada en previsiones |
    Previsiones basadas en ajustes de estacionalidad | Previsión de cantidad por categoría de producto | Previsión de cantidad por plantilla de producto | Previsión de cantidad por productos del proveedor |
    
    Slimme vraagvoorspelling & automatische herbevoorrading voor Odoo | Voorspelling van toekomstige vraag | Voorraadvoorspelling | Automatische aanvulling | 
    Voorspelt toekomstige voorraad | Voorraadbeheer | Automatische aanmaak van inkooporders (PO) op basis van behoefte | Interne magazijnverplaatsingen op basis van voorspellingen | 
    Voorspellingen op basis van seizoensgebonden aanpassingen | Voorspelling aantal per productcategorie | Voorspelling aantal per producttemplate | Voorspelling aantal per leveranciersproducten
    """,
    'description': """""",
    'license': 'OPL-1',

    # Dependencies
    'depends': ['stock', 'purchase', 'sale'],

    # Views
    'data': [
        "security/ir.model.access.csv",
        "views/forecast_rule_view.xml",
        "views/forecast_line_view.xml",
        "views/forecast_seasonality_view.xml",
        "views/transfer_log_view.xml",
        "views/stock_report_line_views.xml",
        # "wizard/forecast_overstock_wizard_views.xml",
        # "wizard/forecast_deadstock_wizard_views.xml",
        # "wizard/deadstock_report_views.xml",
        # "wizard/overstock_report_views.xml",
        "report/report_overstock.xml",
        "report/report_deadstock.xml",
        "report/report_fastmoving_stock.xml",
        "data/cron.xml"
    ],

    # JS/XML Assets for the Custom Print Button
    'assets': {
        'web.assets_backend': [
            'forecasting_auto_replenishment/static/src/js/control_panel_buttons.js',
            'forecasting_auto_replenishment/static/src/xml/control_panel_buttons.xml',
        ],
    },

    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'maintainer': 'Vraja Technologies',
    'website': 'www.vrajatechnologies.com',

    #Technical
    'live_test_url': 'http://www.vrajatechnologies.com/contactus',
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '199',
    'currency': 'EUR',
}
