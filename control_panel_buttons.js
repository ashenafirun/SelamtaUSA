<?xml version="1.0" encoding="UTF-8" ?>
<odoo>
    <data>

        <record id="view_forecast_rule_list" model="ir.ui.view">
            <field name="name">forecast.rule.list</field>
            <field name="model">forecast.rule</field>
            <field name="arch" type="xml">
                <list>
                    <field name="name"/>
                    <field name="company_id"/>
                    <field name="warehouse_id"/>
                    <field name="forecast_period"/>
                    <field name="forecast_method"/>
                </list>
            </field>
        </record>

        <record id="view_forecast_rule_form" model="ir.ui.view">
            <field name="name">forecast.rule.form</field>
            <field name="model">forecast.rule</field>
            <field name="arch" type="xml">
                <form>
                    <sheet>
                        <group>
                            <field name="name" required="1"/>
                            <field name="company_id"/>
                            <field name="warehouse_id" required="1"/>
                            <field name="product_ids" widget="many2many_tags" invisible="1"/>
                            <field name="forecast_rule_config_selection"/>
                            <field name="forecast_rule_product_template_ids" widget="many2many_tags"
                                   invisible="forecast_rule_config_selection in ['vendor', 'category'] or forecast_rule_config_selection == False"
                                   required="forecast_rule_config_selection == 'template'"/>
                            <field name="forecast_rule_vendor_id"
                                   invisible="forecast_rule_config_selection in ['template', 'category'] or forecast_rule_config_selection == False"
                                   required="forecast_rule_config_selection == 'vendor'"/>
                            <field name="product_categ_ids" widget="many2many_tags"
                                   invisible="forecast_rule_config_selection in ['template', 'vendor'] or forecast_rule_config_selection == False"
                                   required="forecast_rule_config_selection == 'category'"/>
                        </group>
                        <group>
                            <group col="1">
                                <group string="Forecast Settings">
                                    <field name="forecast_period"/>
                                    <field name="sales_history_days"/>
                                    <field name="forecast_method"/>
                                </group>
                                <group string="Advance Settings">
                                    <field name="use_seasonality"/>
                                    <field name="seasonality_id" invisible="not use_seasonality"/>
                                </group>
                            </group>
                            <group string="Supply Planning">
                                <field name="lead_time_days"/>
                                <field name="safety_stock_days"/>
                                <field name="order_cycle_days"/>
                                <field name="reordering_rule_selection"/>
                                <field name="min_reorder_qty"
                                       invisible="reordering_rule_selection == 'use_existing_rules_from_product'"/>
                                <field name="reorder_multiple"
                                       invisible="reordering_rule_selection == 'use_existing_rules_from_product'"/>
                                <field name="max_stock_limit"/>
                            </group>
                        </group>
                        <group>

                        </group>
                        <group string="Warehouse Transfer Settings">
                            <group>
                                <field name="source_warehouse_ids" nolabel="1" domain="[('id', '!=', warehouse_id)]">
                                    <list string="Source Warehouses" editable="bottom">
                                        <field name="sequence" widget="handle"/>
                                        <field name="name" string="Source Warehouse"/>
                                    </list>
                                </field>
                            </group>

                            <group>
                                <field name="picking_type_id" domain="[('code','=','internal')]"/>
                                <field name="required_qty"/>
                                <field name="min_transfer_qty"/>
                            </group>
                        </group>
                    </sheet>
                </form>
            </field>
        </record>

        <record id="action_forecast_rule" model="ir.actions.act_window">
            <field name="name">Forecast Rules</field>
            <field name="res_model">forecast.rule</field>
            <field name="view_mode">list,form</field>
        </record>

        <menuitem id="menu_forecast_root"
                  name="Forecast"
                  web_icon="forecasting_auto_replenishment,static/description/forecast.png"/>
        <!--                  sequence="105"-->
        <!--                  parent="stock.menu_stock_inventory_control"-->

        <menuitem id="menu_forecast_rules"
                  name="Forecast Rules"
                  parent="forecasting_auto_replenishment.menu_forecast_root"
                  action="action_forecast_rule"
                  sequence="1"/>
    </data>
</odoo>
