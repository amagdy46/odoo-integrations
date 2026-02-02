# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Odoo 19 integration project with custom addons for Point-of-Sale (POS) and external API integration. The project creates a bridge between Odoo POS and an external Prepit service using webhook-based communication.

## Development Commands

```bash
# Start development environment
docker-compose up

# View logs
docker-compose logs -f web

# Restart with addon update
docker-compose exec web odoo-bin -u prepithelp -d postgres

# Database backup
docker-compose exec db pg_dump -U odoo postgres > backup.sql
```

**Access:** http://localhost:8071 (Odoo UI)

## Architecture

### Folder Structure

```
odoo-integrations/
├── addons/
│   └── prepithelp/          # Prepit integration addon
├── docker-compose.yaml
├── .gitignore
└── CLAUDE.md
```

### Integration Patterns

1. **Webhook-Driven:** POS order events trigger webhooks to external service with stock data
2. **Model Inheritance:** Extends `product.template` and `pos.order` using `_inherit`
3. **System Parameters:** API credentials stored in `ir.config_parameter` for runtime config

### Key Files

- `addons/prepithelp/models/models.py` - POS order hooks, webhook senders, stock integration
- `addons/prepithelp/controllers/controllers.py` - REST endpoint `POST /prepit/order` for external order creation

### Data Flow

```
POS Order Paid → action_pos_order_paid() → Webhook to Prepit (order + stock data)
External Order → POST /prepit/order → _process_order() → Odoo POS Order
```

## Configuration

- **Webhook URL:** Currently hardcoded in `addons/prepithelp/models/models.py:8`
- **Stock threshold:** Low stock set to 2 units in `addons/prepithelp/models/models.py:125`
- **POS Config:** Controller uses fixed config id=1
