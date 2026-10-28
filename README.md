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
- Users (CRUD, roles, activate/deactivate) + **CSV export**
- Properties (full details, multi-photo **lightbox gallery**, Display gallery, Compare, Edit/View)
  - **Bulk actions** (status change / delete selected)
  - **CSV export**
- Clients & Leads pipeline + **CSV export**
- Deals pipeline with stages & commission + **CSV export**
- Appointments / viewings
- Tasks & follow-ups
- Documents with expiry
- Activity log
- Settings: currency (USD/INR/AED), company, support, timezone

### Client portal
- Browse & filter available properties (**price range, bedrooms, listing type, city, type**)
- **Saved Searches** — save filter combinations and re-apply anytime
- Property detail + **multi-photo lightbox gallery** (keyboard arrows + Esc)
- Request viewing
- Favorites
- My appointments
- Profile

### Agent
- **Enhanced Dashboard** with:
  - Stats: properties, available, clients, appointments, pending tasks, open deals, new leads
  - Recent properties list
  - Upcoming appointments
  - Open tasks (priority sorted)
  - Recent leads

## Stack
Flask, Jinja2, SQLite, plain CSS
