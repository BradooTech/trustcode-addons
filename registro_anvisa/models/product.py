# -*- coding: utf-8 -*-
# © 2016 Danimar Ribeiro, Trustcode
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    registro_anvisa = fields.Char(string='Registro Anvisa', size=30)
    validade_anvisa = fields.Date(string='Validade Anvisa')
    esterilizacao = fields.Char(string="Método Esterilizacao", size=100)
