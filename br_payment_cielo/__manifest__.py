# -*- coding: utf-8 -*-
# © 2016 Danimar Ribeiro, Trustcode
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    'name': 'Cielo Checkout Payment Acquirer',
    'category': 'Payment Acquirer',
    'summary': 'Payment Acquirer: Cielo Checkout Implementation',
    'version': '10.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'Trustcode',
    'depends': [
        'account',
        'payment',
        'website_sale',
        'br_base',
        'base',
        'sale',
        'website_contract',
        'subscription'
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/cielo.xml',
        'views/payment_acquirer.xml',
        'views/res_config_view.xml',
        'data/nfs_email_template_data.xml',
        'data/cielo.xml',
    ],
    
    'images': [
        'static/img/email_01.jpg',
        'static/img/email_02.jpg',
        'static/img/email_03.jpg',
        'static/img/email_04.jpg',
        'static/img/email_05.jpg',
        'static/img/email_06.jpg',
        'static/img/email_07.jpg',
        'static/img/email_08.jpg',
        'static/img/email_09.jpg',
        'static/img/email_10.jpg',
        'static/img/email_11.jpg',
        'static/img/email_12.jpg',
        'static/img/email_13.jpg',
        'static/img/email_14.jpg',
    ],
    
    'application': True,
    'installable': True,
}
