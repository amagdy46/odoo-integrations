from odoo import http
from odoo.http import request
import json


class PrepitPOSController(http.Controller):

    @http.route('/prepit/order', type='json', auth='public', methods=['POST'], csrf=False)
    def prepit_order(self, **kwargs):
        """Create a PoS order in Odoo from a Prepit-style JSON payload."""

        # 1) Read raw JSON body
        if request.httprequest.data:
            data = json.loads(request.httprequest.data.decode('utf-8'))
        else:
            data = {}

        PosOrder = request.env['pos.order'].sudo()
        PosConfig = request.env['pos.config'].sudo()

        # 2) Use fixed PoS config id = 1 (change if needed)
        config = PosConfig.browse(1)
        if not config:
            return {'error': 'PoS config 1 not found'}

        # 3) Ensure there is an open PoS session
        session = config.current_session_id
        if not session:
            config.open_ui()
            session = config.current_session_id
        if not session:
            return {'error': 'No open PoS session for config 1'}

        # 4) Required monetary fields
        amount_total = data['amount_total']
        amount_tax = data.get('amount_tax', 0.0)
        amount_paid = data.get('amount_paid', amount_total)
        amount_return = data.get('amount_return', 0.0)

        # 5) Build order dict for _process_order
        order_dict = {
            'config_id': config.id,
            'session_id': session.id,
            'partner_id': data.get('partner_id'),
            'amount_total': amount_total,
            'amount_tax': amount_tax,
            'amount_paid': amount_paid,
            'amount_return': amount_return,
            'lines': [],
            'pricelist_id': config.pricelist_id.id,
        }

        # 6) Lines with required subtotal fields
        for line in data.get('lines', []):
            qty = line['qty']
            price_unit = line['price_unit']
            discount = line.get('discount', 0.0)

            # simple subtotal excl. tax
            price_subtotal = qty * price_unit * (1 - (discount / 100.0))
            # simple subtotal incl. tax (demo: same as excl.)
            price_subtotal_incl = price_subtotal

            line_vals = {
                'product_id': line['product_id'],
                'qty': qty,
                'price_unit': price_unit,
                'discount': discount,
                'price_subtotal': price_subtotal,
                'price_subtotal_incl': price_subtotal_incl,
            }
            order_dict['lines'].append((0, 0, line_vals))

        # 7) Create POS order using internal logic
        new_order_id = PosOrder._process_order(order_dict, existing_order=False)

        return {'order_id': new_order_id}
