# -*- coding: utf-8 -*-

from odoo import models, fields, api

class PaymentTransactionHistoty(models.Model):
    _description = 'Payment Transaction History'
    _name = 'payment.transaction.history'

    payment_transaction_id = fields.Many2one('payment.transaction', string='Payment Transaction ID')
    state = fields.Selection([('error', 'Error'),
    	('done', 'Done')])
    date_now = fields.Datetime(string='Date of Transaction')