# -*- coding: utf-8 -*-

import re
import json
import logging
import requests

from odoo import api, models, fields
from odoo.http import request
from datetime import datetime

_logger = logging.getLogger(__name__)



class AcquirerCielo(models.Model):
    _inherit = 'payment.acquirer'


    provider = fields.Selection(selection_add=[('cielo', 'Cielo')])
    cielo_merchant_id = fields.Char(string='Cielo Merchant Id')
    return_url = fields.Char(string="Url de Retorno", size=300)

    @api.model
    def generate_form(self, partner, product):
        order = self.env['sale.order'].create({'partner_id': partner})
        for item in  product:
            item = self.env['product.template'].search([('default_code','=', item)]).id
            self.env['sale.order.line'].create({'order_id': order.id, 'product_id': item})
        self.env['payment.transaction'].create_transaction(order)
        cielo = self.cielo_form_generate_values(order)
        return cielo

    @api.multi
    def cielo_form_generate_values(self, values):
        merchant_id = self.env['payment.acquirer'].search([('name','=','Cielo')]).cielo_merchant_id
        return_url = self.env['payment.acquirer'].search([('name','=','Cielo')]).return_url
        total_desconto = 0
        items = []
        for line in values.order_line:
            if line.product_id.fiscal_type == 'service':
                tipo = 'Service'
            elif line.product_id.fiscal_type == 'product':
                tipo = 'Asset'
            else:
                tipo = 'Payment'
            total_desconto += line.discount
            item = {
                "Name": line.name, 
                "Description": line.product_id.name, 
                "UnitPrice": "%d" % round(line.price_unit * 100), 
                "Quantity": "%d" % line.product_uom_qty, 
                "Type": tipo, 
            }
            if line.product_id.default_code:
                item["Sku"] = line.product_id.default_code 
            if line.product_id.weight:
                item['Weight'] = "%d" % (line.product_id.weight * 1000) 
            items.append(item)
        address = {
            "Street": values.partner_id.street, 
            "Number": values.partner_id.number, 
            "Complement": values.partner_id.street2, 
            "District": values.partner_id.district, 
            "City": values.partner_id.city_id.name, 
            "State": values.partner_id.state_id.code, 
        }
        if (values.partner_id.street2) > 0:
            address['Complement'] = values.partner_id.street2
        shipping = {
            "Type": "WithoutShipping", 
            "SourceZipCode": re.sub('[^0-9]', '', values.partner_id.zip),
            "TargetZipCode": re.sub('[^0-9]', '', values.partner_id.zip),
        }
        payment = {"BoletoDiscount": 0, "DebitDiscount": 0} 
        if values.template_id.contract_template:
            payment['RecurrentPayment'] = self.check_recurring(values) 
        customer = {
            "Identity": re.sub('[^0-9]', '', values.partner_id.cnpj_cpf or ''),
            "FullName": values.partner_id.name,
            "Email": values.partner_id.email,
            "Phone": re.sub('[^0-9]', '', values.partner_id.phone or ''),
        }
        total_desconto *= 100
        discount = {'Type': 'Amount', 'Value': int(total_desconto)} 
        options = {"AntifraudEnabled": False, "ReturnUrl": return_url}
        order_json = {
            "OrderNumber": values['name'], 
            "SoftDescriptor": self.env['res.company'].search([('id','=',1)]).name.upper(),
            "Cart": { 
                "Discount": discount, 
                "Items": items, 
            },
            "Shipping": shipping,
            "Payment": payment, 
            "Customer": customer,
            "Options": options
        }

        json_send = json.dumps(order_json)
        headers = {"Content-Type": "application/json",
                   "MerchantId": merchant_id}

        request_post = requests.post(
            "https://cieloecommerce.cielo.com.br/api/public/v1/orders",
            data=json_send, headers=headers, verify=False)
        response = request_post.text
        resposta = json.loads(response)

        if "message" in resposta:
            _logger.error(resposta)
            return resposta
        else:
            return {
                'checkout_url': resposta["settings"]["checkoutUrl"]
                }

    @api.multi
    def check_recurring(self, values):
        interval = ''
        if values.template_id.contract_template:
            rec_int = values.template_id.contract_template.recurring_interval
            rec_rule = values.template_id.contract_template.recurring_rule_type
            if rec_rule == 'monthly':
                if rec_int == 1:
                    interval = 'Monthly'
                elif rec_int == 2:
                    interval = 'Bimonthly'
                elif rec_int == 3:
                    interval = 'Quarterly'
                elif rec_int == 5:
                    interval = 'SemiAnnual'
                else:
                    interval = ''
            elif rec_rule == 'yearly':
                if rec_int == 1:
                    interval = 'Annual'
                else:
                    interval = ''

        end_date = values.date_order[0:10]

        return {"Interval": interval, "EndDate": end_date}


class TransactionCielo(models.Model):
    _inherit = 'payment.transaction'

    cielo_transaction_id = fields.Char(string=u'ID Transação')
    state_cielo = fields.Selection(
        [('1', u'Pendente'), ('2', u'Pago'), ('3', u'Negado'),
         ('5', u'Cancelado'), ('6', u'Não Finalizado'), ('7', u'Autorizado')],
        string=u"Situação Cielo")
    transaction_type = fields.Selection(
        [('1', u'Cartão de Crédito'), ('2', u'Boleto Bancário'),
         ('3', u'Débito Online'), ('4', u'Cartão de Débito')],
        string=u'Tipo pagamento')
    payment_installments = fields.Integer(u'Número de parcelas')
    payment_method_brand = fields.Selection(
        [('1', u'Visa'), ('2', u'Mastercard'), ('3', u'American Express'),
         ('4', u'Diners'), ('5', u'Elo'), ('6', u'Aura'), ('7', u'JCB')],
        string=u"Bandeira Cartão")
    payment_boletonumber = fields.Char(string=u"Número boleto", size=100)
    payment_maskedcreditcard = fields.Char(string=u"Número do Cartão de Crédito", size=100)
    tid = fields.Char(string=u"TID")

    url_cielo = fields.Char(
        string=u"Cielo", size=60,
        default="https://www.cielo.com.br/VOL/areaProtegida/index.jsp")

    @api.model
    def _cielo_form_get_tx_from_data(self, data):
        reference = data.get('order_number')
        txs = self.env['payment.transaction'].search(
            [('reference', '=', reference)])
        return txs[0]

    @api.multi
    def _cielo_form_validate(self, data):
        reference = data.get('order_number')
        txn_id = data.get('checkout_cielo_order_number')
        cielo_id = data.get('tid', False)
        payment_type = data.get('payment_method_type')
        amount = float(data.get('amount', '0')) / 100.0
        state_cielo = data.get('payment_status')

        # 1 - Pendente (Para todos os meios de pagamento)
        # 2 - Pago (Para todos os meios de pagamento)
        # 3 - Negado (Somente para Cartão Crédito)
        # 4 - Expirado (Cartões de Crédito e Boleto)
        # 5 - Cancelado (Para cartões de crédito)
        # 6 - Não Finalizado (Todos os meios de pagamento)
        # 7 - Autorizado (somente para Cartão de Crédito)
        # 8 - Chargeback (somente para Cartão de Crédito)
        state = 'pending' if state_cielo == '1' else 'error'
        state = 'done' if state_cielo in ('2', '7') else state

        values = {
            'reference': reference,
            'amount': amount,
            'acquirer_reference': txn_id,
            'state': state,
            'date_validate': datetime.now(),
            'transaction_type': payment_type,
            'cielo_transaction_id': cielo_id,
            'payment_installments': data.get('payment_installments', False),
            'payment_boletonumber': data.get('payment_boletonumber', False),
            'payment_method_brand': data.get('payment_method_brand', False),
            'payment_maskedcreditcard': data.get('payment_maskedcreditcard', False),
            'tid': data.get('tid', False),
            'state_cielo': state_cielo
        }
        res = {}
        res.update({k: v for k, v in values.items() if v})
        return self.write(res)

    @api.multi
    def create_transaction(self, vals):
        cielo_id = self.env['payment.acquirer'].search([('name','=', 'Cielo')]).id
        values = {
            'reference': vals.name,
            'sale_order_id': vals.id,
            'amount': vals.amount_total,
            'currency_id': self.env.user.company_id.currency_id.id,
            'partner_id': vals.partner_id.id,
            'acquirer_id': cielo_id,
        }
        return self.create(values)