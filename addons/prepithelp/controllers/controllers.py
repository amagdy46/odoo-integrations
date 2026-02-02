from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class PrepitPOSController(http.Controller):

    # FIXED: Changed type from 'json' to 'jsonrpc' for Odoo 19 compatibility
    @http.route('/prepit/order', type='jsonrpc', auth='public', methods=['POST'], csrf=False)
    def prepit_order(self, **kwargs):
        """Create a PoS order in Odoo from a Prepit-style JSON payload."""

        # In Odoo type='jsonrpc', kwargs contains the parsed JSON body automatically.
        # No need for json.loads(request.httprequest.data)
        data = kwargs

        PosOrder = request.env['pos.order'].sudo()
        PosConfig = request.env['pos.config'].sudo()

        # 1) Use fixed PoS config id = 1 (Main Shop usually)
        config = PosConfig.browse(1)
        if not config.exists():
            return {'status': 'error', 'message': 'PoS config 1 not found'}

        # 2) Ensure there is an open PoS session
        session = config.current_session_id
        if not session:
            # Attempt to open a session if one isn't active
            config.open_session_cb()
            session = config.current_session_id
            
        if not session:
            return {'status': 'error', 'message': 'No open PoS session for config 1'}

        try:
            # 3) Required monetary fields
            amount_total = data.get('amount_total', 0.0)
            amount_tax = data.get('amount_tax', 0.0)
            amount_paid = data.get('amount_paid', amount_total)
            amount_return = data.get('amount_return', 0.0)

            # 4) Build order dict for Odoo's _process_order
            # Note: Odoo 19 expects the 'data' key inside a specific wrapper for some internal methods,
            # but _process_order generally takes the flattened dict.
            order_dict = {
                'data': {
                    'config_id': config.id,
                    'session_id': session.id,
                    'partner_id': data.get('partner_id'),
                    'amount_total': amount_total,
                    'amount_tax': amount_tax,
                    'amount_paid': amount_paid,
                    'amount_return': amount_return,
                    'lines': [],
                    'pricelist_id': config.pricelist_id.id,
                    'name': data.get('order_ref', 'Prepit External Order'),
                    'pos_reference': data.get('order_ref', 'Prepit External Order'),
                    'creation_date': fields.Datetime.now(),
                }
            }

            # 5) Lines with required subtotal fields
            for line in data.get('lines', []):
                qty = line.get('qty', 1)
                price_unit = line.get('price_unit', 0.0)
                discount = line.get('discount', 0.0)

                # calculation logic
                price_subtotal = qty * price_unit * (1 - (discount / 100.0))
                
                line_vals = [0, 0, {
                    'product_id': line['product_id'],
                    'qty': qty,
                    'price_unit': price_unit,
                    'discount': discount,
                    'price_subtotal': price_subtotal,
                    'price_subtotal_incl': price_subtotal, # Simplified for external sync
                }]
                order_dict['data']['lines'].append(line_vals)

            # 6) Create POS order
            # _process_order returns a list of created order records
            new_order = PosOrder._process_order(order_dict, existing_order=False)

            return {
                'status': 'success',
                'order_id': new_order.id,
                'order_name': new_order.name
            }

        except Exception as e:
            _logger.error("Failed to create Prepit POS order: %s", str(e))
            return {'status': 'error', 'message': str(e)}
