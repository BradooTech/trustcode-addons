# -*- coding: utf-8 -*-

import re
import json
import logging
import requests

from odoo import api, models, fields
from odoo.http import request
from datetime import datetime
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

_logger = logging.getLogger(__name__)


class AcquirerCielo(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('cielo', 'Cielo')])
    cielo_merchant_id = fields.Char(string='Cielo Merchant Id')
    return_url = fields.Char(string="Url de Retorno", size=300)

    @api.model
    def generate_form(self, partner, template_code, coupon=False):
        '''
        Função que é chamada na integração via API com o Odoo
        params: partner: id do cliente(res.partner)
                template_code: codigo do template de cotação
                coupon=Cupom passado pelo cliente para desconto
        workflow: busca o objeto do template de cotação
                cria uma Order de Venda inserindo o partner, template de cotacao e cupon
                chama o metodo calc_validate_cupon_lexis_api que calculo
                para cada linha no template de cotação ele adiciona na linha da Order de Venda
                e para cada linha ele chama o metodo _onchange_discount que carrega o desconto
                cria uma payment transaction com os valores da ordem de venda
                e chama a funcao da cielo
        return: url da cielo
        '''
        template = self.env['sale.quote.template'].search([('code','=', template_code)])
        order = self.env['sale.order'].create({
            'partner_id': partner, 
            'template_id': template.id,
            'cupon_lexis':coupon
            })
        order.calc_validate_cupon_lexis_api()
        for item in template.quote_line:
            line = self.env['sale.order.line'].create({
                'order_id': order.id, 
                'product_id': item.product_id.id
                })
            line._onchange_discount()
        self.env['payment.transaction'].create_transaction(order)
        cielo = self.cielo_form_generate_values(order)
        return cielo

    @api.multi
    def cielo_form_generate_values(self, values):
        '''
        Metodo que recebe os valores da sale.order, faz o post na cielo e retorna a url
        params: values: valor da sale.order
        workflow: recebe a sale.order, trata os valores em um dicionario
                envia o post para a cielo
                verifica se houve erro no retorno, caso sim gera log caso nao retorna a url
        return: erro ou url da cielo
        '''
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
            total_desconto = values.total_desconto
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
            # "SoftDescriptor": self.env['res.company'].search([('id','=',1)]).name.upper(),
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
        '''
        Metodo chamado no cielo_form_generate_values, verifica a periodicidade
            do template de subscription
        return: o intervalo e a end date
        '''
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
    payment_history_id = fields.One2many('payment.transaction.history','payment_transaction_id', string='Payment History')

    url_cielo = fields.Char(
        string=u"Cielo", size=60,
        default="https://www.cielo.com.br/VOL/areaProtegida/index.jsp")

    @api.model
    def _cielo_form_get_tx_from_data(self, data):
        ''' 
        Recebe o dicionario recebido pela Cielo, verifica se esta correto
        e procura uma referencia com o order_number. 
        '''
        reference = data.get('order_number')
        txs = self.env['payment.transaction'].search(
            [('reference', '=', reference)])
        return txs[0]

    @api.multi
    def _cielo_form_validate(self, data):
        '''
        Metodo que recebe o post da cielo e altera os dados caso necessario
        workflow:
            Navega ate a sale.order e grava o retorno e que houve retorno

            Verifica se o amount enviado pela cielo é diferente da sale.order
            Caso sim envia um email informando essa diferença

            Verifica o state se done:
                Grava uma nova data no partner
                Verifica se ja foi criado uma subscription
                Verifica se o status é igual a 2
                    se sim cria o invoice e 
                    Atualiza a data de fim do contrato

            Cria um payment history dessa transação

            Grava o state no partner

        '''
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

        so = self.env['sale.order'].search([('name','=',reference)])
        so.write({'payment_status': state_cielo,'cielo_return':True})
        
        self.partner_id.write({'last_payment_state':state,'sync_lexis':False})            

        if amount != so.amount_total:
            self.write({'amount':amount})
            self.create_and_send_mail()
            

        if state == 'done':
            self.partner_id.write({
                'close_date': (datetime.now() + relativedelta(months=1)),
                'sync_lexis':False,
                'is_trial': False
                })
            if not so.subscription_id:
                so.action_confirm()
            if state_cielo == '2':
                self.create_invoice_nfse()
                sub = self.sale_order_id.subscription_id
                sub.write({
                    'recurring_next_date': (datetime.strptime(sub.recurring_next_date, DEFAULT_SERVER_DATE_FORMAT) + relativedelta(months=1))
                    })

        self.env['payment.transaction.history'].create({
            'payment_transaction_id':self.id,
            'state':state,
            'date_now':datetime.now(),
            'state_cielo':state_cielo
            })


            
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

    
    def action_report_nfse(self, invoice):
        docs = self.env['invoice.eletronic'].search(
            [('invoice_id', '=', invoice.id)])
        if not docs:
            raise UserError(u'Não existe um E-Doc relacionado à esta fatura')
        action = self.env['report'].get_action(
            docs.ids, 'br_nfse.main_template_br_nfse_danfe')
        action['report_type'] = 'qweb-html'
        return action

    @api.multi
    def create_and_send_mail(self):
        '''
        Manda o email do Erro para a Fila de envio
        '''
        template_id = self.env.ref('lexisnexis.mail_template_sync_amount_cielo')
        mail_template = self.env['mail.template'].browse(template_id.id)
        mail_template.send_mail(self.id)

    @api.multi
    def create_transaction(self, vals):
        '''
        Cria uma nova payment transaction com os valores informados
        '''
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

    @api.multi
    def create_invoice_nfse(self):
        '''
        Ao ser chamado, cria um invoice com as lines baseadas na sale.order.
        Ao fim da criação do invoice, cria um Edoc para o invoice ao validar o mesmo (action_invoice_open).
        A nota fiscal é gerada automaticamente na prefeitura (por metodos da localização), então cria-se um report em pdf,
        e adiciona o pdf à um attachment.
        Ao fim da função, um e-mail é criado pelo e-mail template "mail_template_data_lexis_nfse", e, antes do envio do mesmo,
        adicionamos o pdf do report como um attachment.
        '''
        invoice_line_ids_construct = []
        for line in self.sale_order_id.order_line:
            pis_id = line.product_id.taxes_id.search([('domain', '=', 'pis')]).id
            cofins_id = line.product_id.taxes_id.search([('domain', '=', 'cofins')]).id
            tax_issqn_id = line.product_id.taxes_id.search([('domain', '=', 'issqn')]).id
            invoice_line_ids_construct.append(
                (0, 0, {
                    'name': line.name,
                    'origin': self.sale_order_id.name,
                    'account_id': line.product_id.property_account_income_id.id,
                    'price_unit': line.price_subtotal,
                    'quantity': line.product_uom_qty,
                    # 'discount': 0.0,
                    'uom_id': line.product_id.uom_id.id,
                    'product_id': line.product_id.id,
                    'product_type': line.product_id.type,
                    'service_type_id': line.product_id.service_type_id.id,
                    'tax_cofins_id': (cofins_id or False),
                    'tax_pis_id': (pis_id or False),
                    'tax_issqn_id': (tax_issqn_id or False),
                    'pis_cst': line.product_id.tax_cst_pis,
                    'cofins_cst': line.product_id.tax_cst_cofins,
                    'sale_line_ids': [(6, 0, [line.id])],
                    'account_analytic_id': self.sale_order_id.subscription_id.analytic_account_id.id
                    # 'invoice_line_tax_ids': [(6, 0, line.product_id.tax_ids)],
                }))

        invoice = self.env['account.invoice'].create({
            'partner_id': self.sale_order_id.partner_id.id,
            'fiscal_document_id': 35,  # preencher
            'document_serie_id': 3,  # preencher
            'account_id': self.sale_order_id.partner_id.property_account_receivable_id.id,
            'invoice_line_ids': invoice_line_ids_construct,
            'date_invoice': datetime.now().strftime("%Y-%m-%d"),
            'origin': self.sale_order_id.subscription_id.code
        })

        ''' COMENTAR CASO NECESSITE REMOVER A EMISSAO DE NF 
        Comentando para remoção dos dados de envio e geração de nota fiscal'''
        # invoice.action_invoice_open()


        # edoc = self.env['invoice.eletronic'].search([('invoice_id','=',invoice.id)])

        # ReportXml = self.env['ir.actions.report.xml']
        # Report = self.env['report']

        # for doc in edoc:
        #     if doc.state == 'draft':
        '''Função que envia a nota para a prefeitura pela biblioteca pytrustnfe'''
        #         doc.action_send_eletronic_invoice()

        '''Cria o report em pdf e faz o envode pra binário'''
        #         report = ReportXml.search([('model', '=', 'invoice.eletronic'),('name','=','Impressao de NFS-e Paulistana')], limit=1)
        #         bin_pdf = Report.get_pdf([doc.id], 'ir_csll_bradoo.main_template_br_nfse_danfe')
        #         pdf_final = bin_pdf.encode('base64')
        #         attach = self.env['ir.attachment'].create({
        #             'name':'NFse ' + str(doc.partner_id.name),
        #             'res_model':'invoice.eletronic',
        #             'type':'binary',
        #             'datas_fname': 'Nfse.pdf',
        #             'res_id': doc.id,
        #             'datas': pdf_final,
        #             'res_name':'NFse'
        #         })
        '''Busca o Attachment'''
        #         attachment_ids = self.env['ir.attachment'].search([('res_id','=', doc.id),('res_model','=','invoice.eletronic'),('mimetype','=','application/pdf')])
        '''Gera o e-mail pelo template'''
        #         template_id = self.env.ref('br_payment_cielo.mail_template_data_lexis_nfse')
        #         mail_template = self.env['mail.template'].browse(template_id.id)
        #         mail_id = mail_template.send_mail(self.id)
        #         mail = self.env['mail.mail'].browse(mail_id)
        '''adiciona o attachment ao e-mail na fila'''
        #         mail.update({
        #             'attachment_ids':[(4, attachment.id) for attachment in attachment_ids]
        #         })