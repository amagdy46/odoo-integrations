from odoo import models, fields, api
import requests

class ApiIntegration(models.Model):
    _name = 'api.integration.handler' # This is the technical name
    _description = 'Handles Company API Logic'

    def sync_data(self):
        # Retrieve the URL you just saved in the System Parameters
        base_url = self.env['ir.config_parameter'].sudo().get_param('api_integration.url')
        
        # Retrieve the Token (you should create this parameter too)
        token = self.env['ir.config_parameter'].sudo().get_param('api_integration.token')

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        # The actual call to your endpoint
        response = requests.get(f"{base_url}/your_endpoint", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            # Mapping logic goes here...