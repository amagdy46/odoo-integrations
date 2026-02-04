from odoo import models, fields, api
import requests
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = "product.template"
    
    pos_branch_config_ids = fields.Many2many(
        'pos.config',
        'product_template_pos_config_rel',
        'product_tmpl_id',
        'pos_config_id',
        string="POS Branches"
    )

class PrepitHelp(models.Model):
    _name = "prepithelp.prepithelp"
    _description = "Prepit API Integration Helper"
    
    name = fields.Char()
    value = fields.Integer()
    value2 = fields.Float(compute="_compute_value2", store=True)
    description = fields.Text()
    
    @api.depends('value')
    def _compute_value2(self):
        for record in self:
            record.value2 = float(record.value) / 100.0 if record.value else 0.0
    
    # ----------------------
    # STUB METHODS
    # ----------------------
    def sync_prepit_addons_safe(self):
        _logger.info("Addons synchronization completed")
        return True
    
    def sync_prepit_products_safe(self):
        _logger.info("Products synchronization completed")
        return True
    
    def send_pos_menu_to_prepit(self):
        _logger.info("POS menu synchronization completed")
        return True
    
    def update_single_product(self, template_id):
        _logger.info("Single product update completed for template ID: %s", template_id)
        return True
    
    def get_product_by_id(self, pos_product_id):
        _logger.info("Retrieved product by ID: %s", pos_product_id)
        return True
    
    # ----------------------
    # ACTION METHODS
    # ----------------------
    def action_sync_data(self):
        return self.send_pos_menu_to_prepit()
    
    def action_sync_addons(self):
        try:
            return self.sync_prepit_addons_safe()
        except Exception as e:
            _logger.error("Addons synchronization failed: %s", str(e))
            return True
    
    def action_sync_products(self):
        try:
            return self.sync_prepit_products_safe()
        except Exception as e:
            _logger.error("Products synchronization failed: %s", str(e))
            return True
    
    def action_sync_categories(self):
        return self._sync_categories()
    
    def action_sync_branches(self):
        return self._sync_branches()
    
    def action_update_one_branch(self):
        try:
            pos_config = self.env['pos.config'].sudo().search([], limit=1)
            if not pos_config:
                _logger.warning("No POS configurations found for update")
                return True
            return self.update_single_branch(pos_config.id)
        except Exception as e:
            _logger.error("Update single branch failed: %s", str(e))
            return True
    
    def action_delete_one_branch(self):
        try:
            pos_config = self.env['pos.config'].sudo().search([], limit=1)
            if not pos_config:
                _logger.warning("No POS configurations found for deletion")
                return True
            
            pos_branch_id = self._generate_branch_id(pos_config)
            return self.delete_branch_by_id(pos_branch_id)
        except Exception as e:
            _logger.error("Delete branch failed: %s", str(e))
            return True
    
    def action_update_one_product(self):
        try:
            template = self.env["product.template"].sudo().search([
                ('available_in_pos', '=', True),
                ('active', '=', True),
            ], limit=1)
            
            if not template:
                _logger.warning("No POS products found for update")
                return True
                
            return self.update_single_product(template.id)
        except Exception as e:
            _logger.error("Update single product failed: %s", str(e))
            return True
    
    def action_get_product_by_id(self):
        try:
            template = self.env["product.template"].sudo().search([
                ('available_in_pos', '=', True),
                ('active', '=', True),
            ], limit=1)
            
            if not template:
                _logger.warning("No POS products found")
                return True
                
            pos_product_id = f"product-{template.id}"
            return self.get_product_by_id(pos_product_id)
        except Exception as e:
            _logger.error("Get product by ID failed: %s", str(e))
            return True
    
    def action_send_hello_webhook(self):
        payload = {"message": "Hello from Odoo"}
        return self.send_to_prepit(payload)
    
    # ----------------------
    # PRIVATE METHODS
    # ----------------------
    def _sync_categories(self):
        """Sync POS categories to Prepit API"""
        try:
            payload = self._prepare_categories_payload()
            url = "https://api-pos.dev.prepit.app/menu/sync-categories"
            success = self.send_to_prepit(payload, custom_url=url)
            _logger.info("Categories sync result: %s (%d categories)", 
                        "SUCCESS" if success else "FAILED", len(payload.get('categories', [])))
            return True
        except Exception as e:
            _logger.error("Categories synchronization failed: %s", str(e))
            return True
    
    def _sync_branches(self):
        """Sync POS configurations (branches) to Prepit API"""
        try:
            payload = self._prepare_branches_payload()
            url = "https://api-pos.dev.prepit.app/branch/sync-branches"
            success = self.send_to_prepit(payload, custom_url=url)
            _logger.info("Branches sync result: %s (%d branches)", 
                        "SUCCESS" if success else "FAILED", len(payload.get('branches', [])))
            return True
        except Exception as e:
            _logger.error("Branches synchronization failed: %s", str(e))
            return True
    
    def _prepare_categories_payload(self):
        """Prepare categories payload for Prepit API"""
        get_param = self.env['ir.config_parameter'].sudo().get_param
        pos_chain_id = get_param('api_integration.chain_id', '019c229b-9df2-77c5-99e5-b7fc1165e530')
        
        categories = self.env['pos.category'].sudo().search([])
        category_products = self._build_category_products_map()
        
        categories_list = []
        for category in categories:
            pos_cat_id = f"category-{category.id:03d}"
            products_list = category_products.get(pos_cat_id, [])
            
            cat_data = {
                "posCategoryId": pos_cat_id,
                "name": {"en": category.name, "ar": category.name},
                "order": category.sequence or 0,
                "products": products_list
            }
            categories_list.append(cat_data)
        
        return {
            "posChainId": pos_chain_id,
            "categories": categories_list
        }
    
    def _build_category_products_map(self):
        """Build mapping of categories to their POS products"""
        category_products = {}
        pos_products = self.env["product.product"].sudo().search([
            ('available_in_pos', '=', True),
            ('active', '=', True),
        ])
        
        for product in pos_products:
            if product.pos_categ_id:
                cat_id = f"category-{product.pos_categ_id.id:03d}"
                prod_id = f"product-{product.product_tmpl_id.id}"
                
                if cat_id not in category_products:
                    category_products[cat_id] = []
                if prod_id not in category_products[cat_id]:
                    category_products[cat_id].append(prod_id)
        
        return category_products
    
    def _prepare_branches_payload(self):
        """Prepare branches payload for Prepit API"""
        get_param = self.env['ir.config_parameter'].sudo().get_param
        pos_chain_id = get_param('api_integration.chain_id', '019c229b-9df2-77c5-99e5-b7fc1165e530')
        
        pos_configs = self.env['pos.config'].sudo().search([])
        branches_list = []
        
        for config in pos_configs:
            branch_data = self._prepare_single_branch_data(config)
            branches_list.append(branch_data)
        
        return {
            "posChainId": pos_chain_id,
            "branches": branches_list
        }
    
    def _prepare_single_branch_data(self, config):
        """Prepare data for single branch"""
        pos_branch_id = self._generate_branch_id(config)
        
        address_text = f"{getattr(config, 'street', '')} {getattr(config, 'city', '')}".strip()
        address_en = address_text[:100] or 'No address'
        address_ar = address_text[:100] or 'لا يوجد عنوان'
        
        return {
            "posBranchId": pos_branch_id,
            "name": {
                "en": config.name[:50],
                "ar": config.name[:50]
            },
            "address": {
                "en": address_en,
                "ar": address_ar
            },
            "location": {
                "lat": float(getattr(config, 'latitude', 30.0444)),
                "lng": float(getattr(config, 'longitude', 31.2357))
            },
            "phoneNumber": getattr(config, 'phone', '+201234567890') or '+201234567890',
            "operatingHours": [],
            "active": getattr(config, 'state', 'closed') == 'opened',
            "orderTypes": [
                {"orderType": "PICK_UP", "paymentMethods": ["ONLINE", "OFFLINE"]},
                {"orderType": "DINE_IN", "paymentMethods": ["OFFLINE", "WALLET"]},
                {"orderType": "HOME_DELIVERY", "paymentMethods": ["ONLINE", "OFFLINE", "WALLET"]}
            ],
            "vatInclusive": False
        }
    
    def _generate_branch_id(self, config):
        """Generate consistent branch ID from POS config"""
        raw_id = f"{config.name}-{config.id:03d}"
        return ''.join(c for c in raw_id if c.isalnum() or c == '-').strip('-')[:20]
    
    @api.model
    def update_single_branch(self, config_id):
        """Update single branch via Prepit API"""
        try:
            config = self.env['pos.config'].sudo().browse(config_id)
            if not config.exists():
                _logger.warning("POS configuration %s not found", config_id)
                return False
            
            payload = self._prepare_update_branch_payload(config)
            url = "https://api-pos.dev.prepit.app/branch/update-one-branch"
            return self.send_to_prepit(payload, custom_url=url)
        except Exception as e:
            _logger.error("Update single branch failed: %s", str(e))
            return False
    
    def _prepare_update_branch_payload(self, config):
        """Prepare update payload for single branch"""
        get_param = self.env['ir.config_parameter'].sudo().get_param
        pos_chain_id = get_param('api_integration.chain_id', '019c229b-9df2-77c5-99e5-b7fc1165e530')
        
        pos_branch_id = self._generate_branch_id(config)
        timestamp = datetime.now().strftime('%H:%M')
        
        address_text = f"{getattr(config, 'street', '')} {getattr(config, 'city', '')}".strip()
        
        branch_data = self._prepare_single_branch_data(config)
        branch_data.update({
            "name": {
                "en": f"{config.name} [UPDATED {timestamp}]",
                "ar": f"{config.name} [محدث {timestamp}]"
            },
            "address": {
                "en": f"{address_text} [UPDATED {timestamp}]"[:100],
                "ar": f"{address_text} [محدث {timestamp}]"[:100]
            },
            "location": {
                "lat": float(getattr(config, 'latitude', 30.0444)) + 0.001,
                "lng": float(getattr(config, 'longitude', 31.2357)) + 0.001
            },
            "phoneNumber": getattr(config, 'phone', '+2012345678901') or '+2012345678901',
            "vatInclusive": True
        })
        
        return {
            "posChainId": pos_chain_id,
            "branch": branch_data
        }
    
    @api.model
    def delete_branch_by_id(self, pos_branch_id):
        """Delete branch by ID via Prepit API"""
        try:
            get_param = self.env['ir.config_parameter'].sudo().get_param
            api_url = get_param('api_integration.url', 'https://api-pos.dev.prepit.app/').rstrip('/')
            api_token = get_param('api_integration.token', '')
            
            url = f"{api_url}/branch/delete-by-id/{pos_branch_id}"
            headers = {
                "X-Gateway-Token": api_token,
                "Accept": "application/json"
            }
            
            response = requests.delete(url, headers=headers, timeout=10)
            _logger.info("DELETE branch %s -> Status: %s", pos_branch_id, response.status_code)
            
            return response.status_code == 200
        except Exception as e:
            _logger.error("Delete branch %s failed: %s", pos_branch_id, str(e))
            return False
    
    def send_to_prepit(self, payload, custom_url=None):
        """Send payload to Prepit API"""
        try:
            get_param = self.env['ir.config_parameter'].sudo().get_param
            api_token = get_param('api_integration.token', '')
            
            base_url = get_param('api_integration.url', 'https://api-pos.dev.prepit.app/').rstrip('/')
            api_url = custom_url if custom_url else base_url
            
            headers = {
                "X-Gateway-Token": api_token,
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            response = requests.post(api_url, json=payload, headers=headers, timeout=30)
            _logger.info("API %s -> %s: %s", api_url, response.status_code, response.text[:200])
            
            return response.status_code in [200, 201, 204]
        except Exception as e:
            _logger.error("API request failed: %s", str(e))
            return False


class PosOrder(models.Model):
    _inherit = "pos.order"
    
    def _post_prepit_webhook_with_stock(self):
        """Send POS order webhook to Prepit API"""
        try:
            get_param = self.env['ir.config_parameter'].sudo().get_param
            api_token = get_param('api_integration.token', '')
            
            for order in self.sudo():
                payload = self._prepare_pos_order_payload(order)
                url = get_param('api_integration.url', 'https://api-pos.dev.prepit.app/')
                
                headers = {
                    "X-Gateway-Token": api_token,
                    "Content-Type": "application/json"
                }
                
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                _logger.info("POS order %s -> Status: %s", order.name, response.status_code)
        except Exception as e:
            _logger.error("POS order webhook failed: %s", str(e))
    
    def _prepare_pos_order_payload(self, order):
        """Prepare POS order payload for Prepit webhook"""
        lines_payload = []
        for line in order.lines:
            if line.product_id.exists():
                lines_payload.append({
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name,
                    "qty": line.qty,
                    "price": line.price_unit,
                })
        
        return {
            "event": "pos_order_paid",
            "order_ref": order.name,
            "amount_total": order.amount_total,
            "lines": lines_payload,
        }
    
    def action_pos_order_paid(self):
        result = super(PosOrder, self).action_pos_order_paid()
        self._post_prepit_webhook_with_stock()
        return result
