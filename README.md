# Estacle — Real Estate CRM

Python · Flask · HTML · CSS · SQLite

## Run

```bash
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5001**

## Demo logins

| Role     | Email                  | Password     |
|----------|------------------------|--------------|
| Admin    | admin@estacle.com      | admin123     |
| Agent    | agent@estacle.com      | agent123     |
| Customer | customer@estacle.com   | customer123  |

## Features

### Admin
- Dashboard, Analytics, Reports, Global Search, Commission
- Users (CRUD, roles, activate/deactivate) + **CSV export**
- Properties (full details, multi-photo **lightbox gallery**, Display, Compare)
  - **Bulk actions** (status change / delete selected)
  - **CSV export**
- Clients & Leads pipeline + **CSV export**
- Deals pipeline + **CSV export**
- **Property Inquiries** inbox (from clients)
- Appointments / viewings
- Tasks & follow-ups
- Documents with expiry
- Activity log
- Settings: currency (USD / INR / AED)

### Client portal
- Browse & filter (price range, bedrooms, listing type, city, type)
- **Saved Searches** — save and re-apply filter sets
- Property detail + **lightbox photo gallery**
- **Send inquiry** on any property
- Request viewing
- Favorites
- My appointments
- Profile

### Agent
- **Enhanced Dashboard**: properties, clients, appointments, tasks, deals, leads
- **My Properties** list
- Upcoming appointments, open tasks, recent leads

## Stack
Flask, Jinja2, SQLite, plain CSS
