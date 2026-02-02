from odoo import models, fields, api
import json
import requests
import logging

_logger = logging.getLogger(__name__)

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

    def action_sync_data(self):
        """For cron/server action 540 - Hourly Company API Sync."""
        return self.send_pos_menu_to_prepit()

    def action_send_hello_webhook(self):
        """Action button to test the webhook manually from the UI."""
        payload = {"message": "hello odoo"}
        return self.send_to_prepit(payload)

    @api.model
    def send_to_prepit(self, payload):
        """Generic helper to send any payload using System Parameters from your image."""
        get_param = self.env['ir.config_parameter'].sudo().get_param
        
        
        api_url = get_param('api_integration.url', 'https://api-pos.dev.prepit.app/api/v1/odoo/orders')
        api_token = get_param('api_integration.token', '')

        headers = {
            "X-Gateway-Token": api_token,
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=10,
            )
            _logger.info("Prepit API Response (%s): %s", response.status_code, response.text)
        except Exception as e:
            _logger.error("Prepit API Connection failed: %s", str(e))
        return True

    @api.model
    def send_pos_menu_to_prepit(self, config_id=False):
        """Export POS menu for a specific branch (POS config)."""
        ProductTemplate = self.env["product.template"].sudo()
        PosConfig = self.env["pos.config"].sudo()

        domain = [("available_in_pos", "=", True), ("active", "=", True)]

        config_name = False
        if config_id:
            config = PosConfig.browse(config_id)
            if config.exists():
                config_name = config.name
                domain.append(("pos_branch_config_ids", "in", [config_id]))

        templates = ProductTemplate.search(domain)

        items = []
        for t in templates:
            variants = t.product_variant_ids.filtered('active')
            variant_id = variants[:1].id if variants else False
            
            pos_categ_id = t.pos_categ_id.id if hasattr(t, 'pos_categ_id') and t.pos_categ_id else False
            pos_categ_name = t.pos_categ_id.name if pos_categ_id else False

            items.append({
                "product_id": variant_id or t.id,
                "product_name": t.display_name,
                "default_code": t.default_code or "",
                "list_price": t.list_price,
                "pos_category_id": pos_categ_id,
                "pos_category_name": pos_categ_name,
                "active": t.active,
            })

        payload = {
            "event": "pos_menu_export",
            "config_id": config_id,
            "config_name": config_name,
            "items": items,
            "total_items": len(items)
        }
        return self.send_to_prepit(payload)

class PosOrder(models.Model):
    _inherit = "pos.order"

    def _post_prepit_webhook_with_stock(self):
        """Build ONE payload per order with stock info."""
        PrepitHelper = self.env["prepithelp.prepithelp"]
        StockQuant = self.env["stock.quant"].sudo()
        THRESHOLD = 2

        orders_sudo = self.sudo()
        for order in orders_sudo:
            low_stock_items = []
            out_of_stock_items = []
            lines_payload = []

            for line in order.lines:
                product = line.product_id
                if not product.exists():
                    continue
                    
                quants = StockQuant.search([
                    ('product_id', '=', product.id),
                    ('location_id.usage', '=', 'internal')
                ])
                total_stock = sum(quants.mapped('quantity')) if quants else 0.0

                is_low_stock = 0 < total_stock <= THRESHOLD
                is_out_of_stock = total_stock <= 0

                item_data = {
                    "product_id": product.id,
                    "product_name": product.display_name,
                    "stock_remaining": total_stock,
                    "threshold": THRESHOLD,
                }

                if is_low_stock:
                    low_stock_items.append(item_data)
                if is_out_of_stock:
                    out_of_stock_items.append(item_data)

                lines_payload.append({
                    "line_id": line.id,
                    "product_id": product.id,
                    "product_name": product.display_name,
                    "qty": line.qty,
                    "price_unit": line.price_unit,
                    "discount": line.discount,
                    "price_subtotal": line.price_subtotal,
                    "price_subtotal_incl": line.price_subtotal_incl,
                    "tax_ids": line.tax_ids_after_fiscal_position.ids if line.tax_ids_after_fiscal_position else [],
                    "stock_remaining": total_stock,
                    "is_low_stock": is_low_stock,
                    "is_out_of_stock": is_out_of_stock,
                })

            payload = {
                "event": "pos_order_paid",
                "order_ref": order.name,
                "session_id": order.session_id.id if order.session_id else False,
                "config_id": order.session_id.config_id.id if order.session_id and order.session_id.config_id else False,
                "config_name": order.session_id.config_id.name if order.session_id and order.session_id.config_id else False,
                "date_order": fields.Datetime.to_string(order.date_order) if order.date_order else False,
                "amount_total": order.amount_total,
                "amount_tax": order.amount_tax,
                "amount_paid": order.amount_paid,
                "currency": order.currency_id.name if order.currency_id else "USD",
                "status": "paid",
                "lines": lines_payload,
                "has_low_stock_items": bool(low_stock_items),
                "low_stock_items": low_stock_items,
                "has_out_of_stock_items": bool(out_of_stock_items),
                "out_of_stock_items": out_of_stock_items,
            }
            PrepitHelper.send_to_prepit(payload)

    def action_pos_order_paid(self):
        """Trigger webhooks after payment."""
        res = super(PosOrder, self).action_pos_order_paid()
        self._post_prepit_webhook_with_stock()
        
        status_display = self.state
        if self.is_refund:
            status_display = "refunded"
        elif self.state == 'done':
            status_display = "posted"

        payload = {
            "event": "pos_order_status_final",
            "order_ref": self.name,
            "status": status_display,
            "amount_total": self.amount_total,
            "config_id": self.session_id.config_id.id if self.session_id else False,
        }
        self.env["prepithelp.prepithelp"].send_to_prepit(payload)
        return res
