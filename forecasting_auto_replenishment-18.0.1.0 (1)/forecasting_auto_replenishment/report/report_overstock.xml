<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <data>

        <!-- Overstock Report — Excess Stock PDF -->
        <template id="report_overstock_excess_new">
            <t t-call="web.html_container">
                <t t-call="web.external_layout">
                    <div class="page">
                        <h2>Overstock Report — Excess Stock</h2>
                        <p style="color:grey; font-size:11px;">
                            Products where current net stock exceeds forecast + safety stock target.
                        </p>

                        <div style="margin-bottom:12px; font-size:11px; border:1px solid #ddd; padding:8px; border-radius:4px;">
                            <strong>Total Products:</strong> <t t-esc="len(docs)"/>
                            &amp;nbsp;&amp;nbsp;|&amp;nbsp;&amp;nbsp;
                            <strong>Overstocked:</strong>
                            <t t-esc="len(docs.filtered(lambda r: r.status == 'overstock'))"/>
                            &amp;nbsp;&amp;nbsp;|&amp;nbsp;&amp;nbsp;
                            <strong>Normal:</strong>
                            <t t-esc="len(docs.filtered(lambda r: r.status == 'normal'))"/>
                        </div>

                        <table class="table table-sm table-bordered" style="font-size:10px;">
                            <thead style="background-color:#f5f5f5;">
                                <tr>
                                    <th>Product</th>
                                    <th>Warehouse</th>
                                    <th class="text-right">Net Stock</th>
                                    <th class="text-right">Forecast Qty</th>
                                    <th class="text-right">Safety Stock</th>
                                    <th class="text-right">Target Stock</th>
                                    <th class="text-right">Excess Stock</th>
                                    <th class="text-center">Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                <t t-foreach="docs" t-as="line">
                                    <tr t-attf-style="background-color: {{ '#fff0f0' if line.excess_stock > 0 else '#f0fff0' }};">
                                        <td><t t-esc="line.product_id.display_name"/></td>
                                        <td><t t-esc="line.warehouse_id.display_name"/></td>
                                        <td class="text-right"><t t-esc="line.net_stock"/></td>
                                        <td class="text-right"><t t-esc="line.forecast_qty"/></td>
                                        <td class="text-right"><t t-esc="line.safety_stock"/></td>
                                        <td class="text-right"><t t-esc="line.target_stock"/></td>
                                        <td class="text-right">
                                            <span t-attf-style="color:{{ 'red' if line.excess_stock > 0 else 'green' }}; font-weight:bold;">
                                                <t t-esc="line.excess_stock"/>
                                            </span>
                                        </td>
                                        <td class="text-center">
                                            <span t-if="line.status == 'overstock'" style="color:red; font-weight:bold;">Overstock</span>
                                            <span t-else="" style="color:green; font-weight:bold;">Normal</span>
                                        </td>
                                    </tr>
                                </t>
                            </tbody>
                        </table>
                    </div>
                </t>
            </t>
        </template>

        <!-- Overstock Report — Days of Inventory PDF -->
        <template id="report_overstock_days_new">
            <t t-call="web.html_container">
                <t t-call="web.external_layout">
                    <div class="page">
                        <h2>Overstock Report — Days of Inventory</h2>
                        <p style="color:grey; font-size:11px;">
                            Products where days of inventory on hand exceed the rule's forecast period.
                        </p>

                        <table class="table table-sm table-bordered" style="font-size:10px;">
                            <thead style="background-color:#f5f5f5;">
                                <tr>
                                    <th>Product</th>
                                    <th>Warehouse</th>
                                    <th class="text-right">Net Stock</th>
                                    <th class="text-right">Avg Daily Demand</th>
                                    <th class="text-right">Days of Inventory</th>
                                    <th class="text-right">Target Days</th>
                                    <th class="text-right">Excess Days</th>
                                    <th class="text-center">Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                <t t-foreach="docs" t-as="line">
                                    <tr t-attf-style="background-color: {{ '#fff0f0' if line.days_of_inventory > line.target_days else '#f0fff0' }};">
                                        <td><t t-esc="line.product_id.display_name"/></td>
                                        <td><t t-esc="line.warehouse_id.display_name"/></td>
                                        <td class="text-right"><t t-esc="line.net_stock"/></td>
                                        <td class="text-right"><t t-esc="line.avg_daily_demand"/></td>
                                        <td class="text-right">
                                            <span t-attf-style="color:{{ 'red' if line.days_of_inventory > line.target_days else 'green' }}; font-weight:bold;">
                                                <t t-esc="line.days_of_inventory"/>
                                            </span>
                                        </td>
                                        <td class="text-right"><t t-esc="line.target_days"/></td>
                                        <td class="text-right">
                                            <span t-attf-style="color:{{ 'red' if line.excess_days > 0 else 'green' }}; font-weight:bold;">
                                                <t t-esc="line.excess_days"/>
                                            </span>
                                        </td>
                                        <td class="text-center">
                                            <span t-if="line.status == 'overstock'" style="color:red; font-weight:bold;">Overstock</span>
                                            <span t-else="" style="color:green; font-weight:bold;">Normal</span>
                                        </td>
                                    </tr>
                                </t>
                            </tbody>
                        </table>
                    </div>
                </t>
            </t>
        </template>

    </data>
</odoo>