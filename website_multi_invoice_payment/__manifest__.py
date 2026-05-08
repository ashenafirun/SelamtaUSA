# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.

{
    "name": "Website Multi Invoice Payment",
    "version": "18.0.1.0.0",
    "summary": "Allow to pay multiple invoice to portal users from website",
    "sequence": 30,
    "description": """
Allow to pay multiple invoice to portal users from website.

    website partial invoice payment
website
Invoice
invoice payment
partial invoice
partial invoice payment
website invoice
website invoice payment
portal user
website portal
portal customer
customer portal
customer portal payment
customer portal partial payment
multi invoice
website portal user multi invoice payment
multi invoice payment
multi invoice ecommerce
multiple invoice payment
multiple
multiple payment

Financial
Account
Financial account
balance sheet
income statement
profit and loss
general ledger
trial balance
aged partner balance
journal audit
financial report
account report
debit account
credit account
debit and credit account
credit and debit account
Asset
Tangible asset
Intangible asset
asset depreciation
depreciation
sell assets
dispose assets
assets report
assets journal entries
Account partner
Account balance
Account balance report
Aged partner balance report
aged partner report
account fiscal year
fiscal year
aged partner excel report
aged partner pdf report
Budget
Account Budget management
account budget
budget on project
budget on department
budget on company
budget on employee
income account
expense account
Tax
Tax Report
Account Tax Report
Advance filter
tax advance filter
account tax report on pdf
account tax report on excel
account sales tax report
account purchase tax report
sales tax
purchase tax
sales tax report
purchase tax report
account alert
account budget alert
account budget warning
account warning
warning
budget alert
budget warning
over budget alert
purchase warning
purchase alert
alert on purchase order
alert on purchase
purchase order alert
purchase order warning
warning on purchase order
warning on vendor bill
vendor bill warning
alert on vendor bill
vendor bill alert
Multi branches
company branches
branch on crm
branch on sales
branch on purchase
branch on account
branch on warehouse
branch on location
branch on stock operation
branch on stock
branch to branch transaction
stock move
stock move branch to branch
transfer stock branch to branch
stock transfer branch to branch
chart of account for branch
branch on picking
branch on vendor bills
inventory adjustment
inventory adjustment on branch
sales receipt branch wise
branch wise sales receipt
branch wise purchase receipt
branch wise journal entries
journal entries branch wise
branch wise payment
account journal
account journal audit
account journal audit report
account excel
account pdf
account audit
account audit report
account audit excel
account audit pdf
account journal excel
account journal pdf
account trial balance
account trial balance report
Trial balance report
trial balance period
trial balance comparison
account balance comparison
account trial balance report excel
account trial balance report pdf
trial balance report excel
trial balance report pdf
Analytic Account report
Analytic account
Analytic report
budget report
account budget report
multi level analytic report
multi level analytic account report
department budget
project budget
cost of project
cost of department
analytic account excel report
analytic account pdf report
excel report
pdf report
account excel report
account pdf report
Open Fiscal year
Close Fiscal year
Fiscal period
Cancel opening entry in fiscal year
Cancel closing entry in fiscal year
period
yearly
tax year
revenue
taxation
monetary
economy
circulate
financial year
journal entry
opening balance
closing balance
debt
profit & loss
agent
policy
imbalance
transparency
stance
effort
policies
year end
new year
company
audit
payment
customer
customer payment
customer payment overdue
overdue customer payment
customer overdue payment reminder
customer overdue payment follow up
mail
payment reminder mail
due days
payment due
due payment
scheduler
analysis
follow up analysis
Accounting & Auditing Terms
accounting
accounting concepts
financial management
marginal benefit
letter of credit
buyer
amount due
due amount
demand
cash
cash on delivery
deferred payment
duration
provision
cash flow
entrepreneur
monitoring
sale
feedback
requirement
effectiveness
following
auditing
management
contract management
payment term
warning/alert
purchase
vendor bill
Budgetary Positions
Planned Amount
Alert Types
budget limit
ignore
restrict
allow manager
purchase manager
account manager
purchase order
vendor bills
Odoo ERP Installation
Odoo ERP Migration
Digital Strategy
Odoo ERP configuration
Odoo ERP Staffing
Digital Technology Selection
Odoo ERP Customization
Odoo Functional Training
Digital Transformation Implementation
Odoo ERP New Module Development
Odoo ERP Technical Training
Legacy Modernization
Odoo ERP Integrations
Odoo ERP Support
Organizational Transformation
    """,
    "category": "Website",
    "author": "Synconics Technologies Pvt. Ltd.",
    "website": "https://www.synconics.com/",
    "depends": ["account_payment", "website_payment"],
    "data": [
        "security/ir_rules.xml",
        "views/account_portal_templates.xml",
    ],
    "demo": [],
    "images": ["static/description/main_screen.png"],
    "assets": {
        "web.assets_frontend": [
            "website_multi_invoice_payment/static/src/js/multi_invoice_payment.js",
            "website_multi_invoice_payment/static/src/css/multi_invoice.css",
        ]
    },
    "price": 50.0,
    "license": "OPL-1",
    "currency": "EUR",
    "installable": True,
    "application": True,
    "auto_install": False,
}
