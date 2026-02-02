import requests
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class ApiSyncHandler(models.Model):
    _name = 'api.sync.handler'
    _description = 'Logic for syncing external API data'

    def action_sync_data(self):
        # Configuration
        params = self.env['ir.config_parameter'].sudo()
        url = params.get_param('api_integration.url')
        token = params.get_param('api_integration.token')

        if not url or not token:
            raise UserError(_("Configuration Error: Please set API URL and Token in System Parameters."))

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        try:
            
            response = requests.get(f"{url.rstrip('/')}/your_endpoint", headers=headers, timeout=15)
            response.raise_for_status()
            data_list = response.json()

            
            for item in data_list:
                
                external_id = str(item.get('id'))
                existing = self.env['res.partner'].search([('ref', '=', external_id)], limit=1)

                
                vals = {
                    'name': item.get('full_name'),
                    'email': item.get('email'),
                    'phone': item.get('phone_no'),
                    'ref': external_id,
                    'is_company': True,
                }

               
                if existing:
                    existing.write(vals)
                else:
                    self.env['res.partner'].create(vals)

            return True

        except requests.exceptions.RequestException as e:
            _logger.error("API Sync Failed: %s", e)
            raise UserError(_("Network Error: Could not connect to the external API."))
        except Exception as e:
            _logger.error("Unexpected Error: %s", e)
            raise UserError(_("An unexpected error occurred during the sync process."))
