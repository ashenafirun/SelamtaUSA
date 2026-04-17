<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <data>

        <!-- Deadstock Report PDF -->
        <template id="report_deadstock_new">
            <t t-call="web.html_container">
                <t t-call="web.external_layout">
                    <div class="page">
                        <h2>Deadstock Report</h2>
                        <p style="color:grey; font-size:11px;">
                            Products with no stock movement — sorted by longest inactive first.
                        </p>

                        <!-- Summary -->
                        <div style="margin-bottom:12px; font-size:11px; border:1px solid #ddd; padding:8px; border-radius:4px;">
                            <strong>Total Products:</strong> <t t-esc="len(docs)"/>
                            &amp;nbsp;&amp;nbsp;|&amp;nbsp;&amp;nbsp;
                            <strong>Deadstock (120+ days):</strong>
                            <t t-esc="len(docs.filtered(lambda r: r.status == 'deadstock'))"/>
                            &amp;nbsp;&amp;nbsp;|&amp;nbsp;&amp;nbsp;
                            <strong>Very Slow Moving (60–120 days):</strong>
                            <t t-esc="len(docs.filtered(lambda r: r.status == 'very_slow'))"/>
                            &amp;nbsp;&amp;nbsp;|&amp;nbsp;&amp;nbsp;
                            <strong>Slow Moving (30–60 days):</strong>
                            <t t-esc="len(docs.filtered(lambda r: r.status == 'slow'))"/>
                        </div>

                        <table class="table table-sm table-bordered" style="font-size:10px;">
                            <thead style="background-color:#f5f5f5;">
                                <tr>
                                    <th>Product</th>
                                    <th>Warehouse</th>
                                    <th class="text-right">Current Stock</th>
                                    <th class="text-right">Last Movement</th>
                                    <th class="text-right">Days Since Movement</th>
                                    <th class="text-center">Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                <t t-foreach="docs" t-as="line">
                                    <t t-set="bg" t-value="
                                        '#ffcccc' if line.status == 'deadstock'
                                        else '#ffe5cc' if line.status == 'very_slow'
                                        else '#fff5cc' if line.status == 'slow'
                                        else '#ffffff'
                                    "/>
                                    <t t-set="color" t-value="
                                        'red' if line.status == 'deadstock'
                                        else 'orange' if line.status == 'very_slow'
                                        else '#b8860b' if line.status == 'slow'
                                        else 'green'
                                    "/>
                                    <t t-set="label" t-value="
                                        'Deadstock' if line.status == 'deadstock'
                                        else 'Very Slow Moving' if line.status == 'very_slow'
                                        else 'Slow Moving' if line.status == 'slow'
                                        else 'Active'
                                    "/>
                                    <tr t-attf-style="background-color:{{ bg }};">
                                        <td><t t-esc="line.product_id.display_name"/></td>
                                        <td><t t-esc="line.warehouse_id.display_name"/></td>
                                        <td class="text-right"><t t-esc="line.current_stock"/></td>
                                        <td class="text-right"><t t-esc="line.last_movement or '—'"/></td>
                                        <td class="text-right"><t t-esc="line.days_since_movement if line.days_since_movement != 999 else 'Never'"/></td>
                                        <td class="text-center">
                                            <span t-attf-style="color:{{ color }}; font-weight:bold;">
                                                <t t-esc="label"/>
                                            </span>
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
