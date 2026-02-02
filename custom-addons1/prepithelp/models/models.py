from odoo import models, fields, api
import json
import requests
import logging

_logger = logging.getLogger(__name__)

WEBHOOK_URL = "https://webhook.site/7a544631-0b9b-47b9-be96-ee1cf237c433"

class ProductTemplate(models.Model):
    _inherit = "product.template"

    pos_branch_config_ids = fields.Many2many(
        'pos.config',
        'product_template_pos_config_rel',
        'product_tmpl_id',
        'pos_config_id',
        string="POS Branches",
        help="Select the POS branches (POS configs) where this product is available."
    )

class PrepitHelp(models.Model):
    _name = "prepithelp.prepithelp"
    _description = "Prepit helper"

    name = fields.Char()
    value = fields.Integer()
    value2 = fields.Float(compute="_value_pc", store=True)
    description = fields.Text()

    @api.depends("value")
    def _value_pc(self):
        for record in self:
            record.value2 = float(record.value) / 100 if record.value else 0.0

    def action_send_hello_webhook(self):
        webhook_url = WEBHOOK_URL
        payload = {"message": "hello odoo"}
        headers = {"Content-Type": "application/json"}
        requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers=headers,
            timeout=10,
        )
        return True

    @api.model
    def send_to_prepit(self, payload):
        """Generic helper to send any payload to Prepit/webhook."""
        webhook_url = WEBHOOK_URL
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(
                webhook_url,
                data=json.dumps(payload),
                headers=headers,
                timeout=10,
            )
            _logger.info("Preptit webhook sent: %s", response.status_code)
        except Exception as e:
            _logger.error("Preptit webhook failed: %s", str(e))
        return True

    @api.model
    def send_pos_menu_to_prepit(self, config_id=False):
        """
        Export POS menu for a specific branch (POS config).
        Each product is included only if:
        - available_in_pos = True
        - its template has this config in pos_branch_config_ids
        """
        Product = self.env["product.product"].sudo()
        PosConfig = self.env["pos.config"].sudo()

        domain = [("available_in_pos", "=", True)]

        config_name = False
        if config_id:
            config = PosConfig.browse(config_id)
            if config.exists():
                config_name = config.name
                domain.append(("product_tmpl_id.pos_branch_config_ids", "in", config_id))

        products = Product.search(domain)

        items = []
        for p in products:
            items.append(
                {
                    "product_id": p.id,
                    "product_name": p.display_name,
                    "default_code": p.default_code,
                    "list_price": p.lst_price,
                    "pos_category_id": p.pos_categ_id.id if p.pos_categ_id else False,
                    "pos_category_name": p.pos_categ_id.name if p.pos_categ_id else False,
                    "active": p.active,
                }
            )

        payload = {
            "event": "pos_menu_export",
            "config_id": config_id,
            "config_name": config_name,
            "items": items,
        }

        self.send_to_prepit(payload)
        return True

class PosOrder(models.Model):
    _inherit = "pos.order"

    def _post_prepit_webhook_with_stock(self):
        """
        Build ONE payload per order:
        - full order details
        - line details
        - stock info for each product
        - separate low-stock / out-of-stock items
        """
        PrepitHelper = self.env["prepithelp.prepithelp"]
        StockQuant = self.env["stock.quant"].sudo()

        THRESHOLD = 2

        for order in self:
            low_stock_items = []
            out_of_stock_items = []
            lines_payload = []

            for line in order.lines:
                product = line.product_id

                quants = StockQuant.search([
                    ('product_id', '=', product.id),
                    ('location_id.usage', '=', 'internal')
                ])
                total_stock = sum(q.quantity for q in quants)
                stock_remaining = total_stock

                is_low_stock = total_stock > 0 and total_stock <= THRESHOLD
                is_out_of_stock = total_stock == 0

                if is_low_stock:
                    low_stock_items.append({
                        "product_id": product.id,
                        "product_name": product.display_name,
                        "stock_remaining": total_stock,
                        "threshold": THRESHOLD,
                    })

                if is_out_of_stock:
                    out_of_stock_items.append({
                        "product_id": product.id,
                        "product_name": product.display_name,
                        "stock_remaining": total_stock,
                        "threshold": THRESHOLD,
                    })

                lines_payload.append(
                    {
                        "line_id": line.id,
                        "product_id": product.id,
                        "product_name": product.display_name,
                        "qty": line.qty,
                        "price_unit": line.price_unit,
                        "discount": line.discount,
                        "price_subtotal": line.price_subtotal,
                        "price_subtotal_incl": line.price_subtotal_incl,
                        "tax_ids": [t.id for t in line.tax_ids_after_fiscal_position],
                        "stock_remaining": stock_remaining,
                        "is_low_stock": is_low_stock,
                        "is_out_of_stock": is_out_of_stock,
                    }
                )

            stock_message = ""
            if out_of_stock_items:
                stock_message = "This product is out of stock."
            elif low_stock_items:
                stock_message = "This product has low stock."

            payload = {
                "event": "pos_order_paid",
                "order_ref": order.name,
                "session_id": order.session_id.id,
                "config_id": order.session_id.config_id.id,
                "config_name": order.session_id.config_id.name,
                "date_order": str(order.date_order),
                "amount_total": order.amount_total,
                "amount_tax": order.amount_tax,
                "amount_paid": order.amount_paid,
                "pricelist_id": order.pricelist_id.id,
                "currency": order.pricelist_id.currency_id.name,
                "delivery_status": "pending",
                "status": "paid",
                "lines": lines_payload,
                "has_low_stock_items": bool(low_stock_items),
                "low_stock_items": low_stock_items,
                "has_out_of_stock_items": bool(out_of_stock_items),
                "out_of_stock_items": out_of_stock_items,
                "stock_message": stock_message,
            }

            PrepitHelper.send_to_prepit(payload)

    def send_delivery_status_to_prepit(self, status="delivered"):
        """Send only delivery status update for this order to Preptit."""
        PrepitHelper = self.env["prepithelp.prepithelp"]
        for order in self:
            payload = {
                "event": "pos_order_delivery_update",
                "order_ref": order.name,
                "session_id": order.session_id.id,
                "config_id": order.session_id.config_id.id,
                "config_name": order.session_id.config_id.name,
                "date_order": str(order.date_order),
                "delivery_status": status,
            }
            PrepitHelper.send_to_prepit(payload)

    def send_status_to_prepit(self, status):
        """
        Optional simple status update for other flows.
        """
        PrepitHelper = self.env["prepithelp.prepithelp"]
        for order in self:
            payload = {
                "event": "pos_order_status_update",
                "order_ref": order.name,
                "session_id": order.session_id.id,
                "config_id": order.session_id.config_id.id,
                "config_name": order.session_id.config_id.name,
                "date_order": str(order.date_order),
                "status": status,
            }
            PrepitHelper.send_to_prepit(payload)

    def action_pos_order_paid(self):
        """
        When POS order is paid → Send webhooks AFTER super() completes.
        FIXED: Proper refund detection + status mapping.
        """
        res = super(PosOrder, self).action_pos_order_paid()
        
        # Send full order + stock data
        self._post_prepit_webhook_with_stock()
        
        # Send status webhook with proper refund detection
        PrepitHelper = self.env["prepithelp.prepithelp"]
        
        # FIXED: Detect refund status properly
        status_display = self.state
        if self.is_refund:
            status_display = "refunded"
        elif self.state == 'done':
            status_display = "posted"
        elif self.state == 'cancel':
            status_display = "cancelled"
            
        payload = {
            "event": "pos_order_status_final",
            "order_ref": self.name,
            "pos_reference": self.pos_reference,
            "uuid": self.uuid,
            "status": status_display,  # paid, refunded, posted, cancelled
            "state": self.state,       # raw Odoo state
            "is_refund": self.is_refund,
            "amount_total": self.amount_total,
            "session_id": self.session_id.id if self.session_id else False,
            "config_id": self.session_id.config_id.id if self.session_id and self.session_id.config_id else False,
        }
        PrepitHelper.send_to_prepit(payload)
        _logger.info("Preptit status sent: %s -> %s", self.name, status_display)
        
        return res




















# from odoo import models, fields, api
#
#
# class PrepitHelp(models.Model):
#     # Technical name of the model used by Odoo ORM
#     _name = 'prepithelp.prepithelp'
#     # Human‑readable description of the model
#     _description = 'prepithelp.prepithelp'
#
#     # Character field to store the record name
#     name = fields.Char()
#     # Integer field to store a numeric value
#     value = fields.Integer()
#     # Float field automatically computed from `value`, stored in database
#     value2 = fields.Float(compute="_value_pc", store=True)
#     # Text field for a longer free‑form description
#     description = fields.Text()
#
#     # When `value` changes, recompute `value2`
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             # Example: if value = 200, value2 becomes 2.0
#             record.value2 = float(record.value) / 100
