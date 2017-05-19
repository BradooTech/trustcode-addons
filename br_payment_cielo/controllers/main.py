# -*- coding: utf-8 -*-
# © 2016 Danimar Ribeiro, Trustcode
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).


import logging
import pprint

from odoo import http, api
from odoo.http import request

_logger = logging.getLogger(__name__)


class CieloController(http.Controller):
    _notify_url = '/cielo/notificacao/'
    _status_url = '/cielo/status/'

    @http.route('/cielo/notificacao/', type='http', auth="none", methods=['GET', 'POST'], csrf=False)
    def cielo_notify(self, **post):
        """ Cielo Notificação"""
        _logger.info(u'Iniciando retorno de notificação cielo post-data: %s',
                     pprint.pformat(post))
        self._cielo_validate_data(**post)
        return "<status>OK</status>"

    @http.route('/cielo/status/', type='http', auth="none",
                methods=['GET', 'POST'], csrf=False)
    def cielo_status(self, **post):
        _logger.info(
            u'Iniciando mudança de status de transação post-data: %s',
            pprint.pformat(post))  # debug
        self._cielo_validate_data(**post)
        return "<status>OK</status>"


    @api.multi
    def _cielo_validate_data(self, **post):
        res = request.env['payment.transaction'].sudo().form_feedback(post,'cielo')
        return res