{
    'name': 'nagaad',
    'version': '1.0.0',
    'category': 'nagaad',
    'summary': 'Nagaad Management System',
    'description': "Mohamed Dahir",
    'depends': ['mail', 'point_of_sale', 'web'],
    'application': True,
    'sequence': -100,
    'author': 'mdc',

    'assets': {
        'web.assets_common': [
            # Add any global SCSS or JS files here
        ],
        'point_of_sale.assets': [
            'idil/static/src/js/pos_customer_modification.js',
        ],
        'web.assets_backend': [
            'idil/static/src/css/kanban.css',
            # Include your custom JS here if needed
        ],
        'web._assets_primary_variables': [
            ('prepend', 'idil/static/src/scss/primary_variables.scss'),
        ],
    },

    'data': [
        'security/ir.model.access.csv',
        'data/transaction_source_data.xml',
        'data/seq_journal_entry.xml',
        'data/groups.xml',
        'data/restaurant_chart_of_accounts.xml',
        'data/customer_types.xml',  # Customer Types XML data
        'data/unit_measures.xml',  # Unit Measures XML data
        'data/item_categories.xml',  # Item Categories XML data
        'data/idil_sequence.xml',
        'data/ir_sequence_data.xml',
        'data/delete.xml',
        'data/booking_sequence.xml',
        'data/purchase_sequence.xml',
        'views/customer_view.xml',
        'views/vendor_view.xml',
        'views/custypes_view.xml',
        'views/item_view.xml',
        'views/unit_measure_view.xml',
        'views/item_category_view.xml',
        'views/chart_of_accounts_views.xml',
        'views/purchase_view.xml',
        'views/view__purchase_order.xml',
        'views/BOM.xml',
        'views/bom_type_view.xml',
        'views/product_views.xml',
        'views/view_manufacturing_order.xml',
        'reports/Account_balance_report.xml',
        'reports/Vendor_balance_report.xml',
        'reports/vendor_transaction_report.xml',
        'reports/Product_Stock_report.xml',
        'views/vendor_bills.xml',
        'views/trx_source.xml',
        'views/pos_menu_view.xml',
        'views/pos_session_view.xml',
        'views/pos_payment_method_views.xml',
        'views/idil_employee_views.xml',
        'views/kitchen_views.xml',
        'views/kitchen_transfer_views.xml',
        'views/view_trial_balance.xml',
        'views/kitchen_cook.xml',
        'views/transaction_booking_views.xml',
        'views/view_journal_entry.xml',
        'views/vendor_transaction_views.xml',
        'views/report_income_statement.xml',
        'views/template_override.xml',
        'views/view_commission.xml',
        'views/CurrencyExchange.xml',
        'views/company_trial_balance.xml',
        'views/income_statement.xml',
        'views/payment_wizard_form.xml',
        'views/idil_hall_view.xml',
        'views/idil_hall_booking_view.xml',
        'views/idil_hall_facility_view.xml',
        'views/idil_hall_schedule_view.xml',
        'views/idil_hall_booking_calendar_view.xml',
        'views/idil_hall_payment_view.xml',
        'views/idil_hall_pricing_rule_view.xml',
        'views/idil_hall_dashboard_view.xml',
        'views/balance_sheet_report.xml',
        'views/custom_pos_template.xml',
        'views/menu.xml',
    ],

    'controllers': [
        'controllers/item_api_controller.py',
        'product_api_controller.py', 
        'order_api_controller.py'
        'test_api_controller.py'
    ],
}
