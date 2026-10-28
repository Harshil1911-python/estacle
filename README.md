# Estacle — Real Estate CRM

Python · Flask · HTML · CSS · SQLite

## Run

```bash
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5001**

## Demo logins

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@estacle.com | admin123 |
| Agent | agent@estacle.com | agent123 |
| Customer | customer@estacle.com | customer123 |

## Features

### Admin
- Dashboard, Analytics, Reports, Global Search, Commission
- Users (CRUD, roles, activate/deactivate)
- Properties (full details, photos, Display gallery, Compare, Edit/View)
- Clients & Leads pipeline
- Deals pipeline with stages & commission
- Appointments / viewings
- Tasks & follow-ups
- Documents with expiry
- Activity log
- Settings: currency (USD/INR/AED), company, support, timezone

### Client portal
- Browse & filter available properties
- Property detail + photo gallery
- Request viewing
- Favorites
- My appointments
- Profile

### Agent
- Dashboard with assigned stats

## Stack
Flask, Jinja2, SQLite, plain CSS
