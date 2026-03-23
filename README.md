# Factuurcontrole Platform

Factuurcontrole Platform is a Django-based replacement for the existing Power BI invoice-control dashboards. It synchronizes client-specific SQL Server control data into Parquet, queries that data with DuckDB, and serves dashboards and control detail pages through Django templates.

## Purpose And Scope

- Read invoice-control data per client from SQL Server
- Keep current and history Parquet datasets per client
- Support both:
  - `RG` runs via `gecontroleerdeRittenDetail` and `gecontroleerdeRoutesDetail`
  - `VA` runs via `gecontroleerdeVARittenDetail`
- Use `stuurtabel2_last` as the current-run source of truth
- Filter dashboards by `stuurtabel_id`
- Show executed controls from `controle` + `controleDone`
- Build dedicated control report pages over the synced data

Not done yet:

- no finalized per-control deviation logic
- no optimized history deduplication yet
- no full control-page coverage beyond the first implemented pages

## Architecture

```text
SQL Server (per client, schema facturatie)
    -> sync_pipeline/
    -> Parquet datasets in data/client=<slug>/
    -> DuckDB queries in backend/apps/analytics/services.py
    -> Django views/templates in backend/apps/dashboards/
```

Main dataset families:

- `manifest`
- `ritten_detail`
- `routes_detail`
- `va_ritten_detail`
- `executed_controls`
- `ritten_controls_long`
- `routes_controls_long`
- `va_ritten_controls_long`

## Exact Environment Used Here

- Python `3.13.5`
- Django `5.2.12`
- duckdb `1.5.0`
- pandas `3.0.1`
- pyarrow `23.0.1`
- pyodbc `5.3.0`
- python-dotenv `1.2.2`
- psycopg `3.3.3`
- Local environment: `.venv` created with `python -m venv .venv`
- Working SQL Server ODBC driver on this machine: `ODBC Driver 17 for SQL Server`

## Repository Layout

```text
backend/           Django project, apps, admin, management commands
sync_pipeline/     SQL Server extraction and Parquet sync pipeline
analytics/         Shared SQL files
templates/         Django templates
static/            Static assets
data/              Local Parquet datasets + analytics.duckdb
uploads/           Reference files provided during development
scripts/           Utility scripts
todo.md            Open follow-up items
```

## Install And Start

1. Create and activate the existing-style virtualenv:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   or:

   ```bash
   pip install -e .
   ```

3. Create `.env`:

   ```bash
   cp .env.example .env
   ```

4. Local minimum `.env`:

   ```env
   DEBUG=True
   SECRET_KEY=change-me
   ALLOWED_HOSTS=127.0.0.1,localhost
   ```

5. Run migrations:

   ```bash
   cd backend
   python manage.py migrate
   ```

6. Create the admin user:

   ```bash
   python manage.py createsuperuser
   ```

7. Start Django:

   ```bash
   python manage.py runserver
   ```

Application URLs:

- Dashboard: `http://127.0.0.1:8000/`
- Admin: `http://127.0.0.1:8000/admin/`
- Login: `http://127.0.0.1:8000/accounts/login/`

## Configure Application

There is no separate seed command yet. Initial setup is done in Django admin.

Create:

1. `Client`
2. `DataSourceConfig`
3. `SyncConfig`
4. `ClientAccess`

For the current source system, `DataSourceConfig.extra_params` must include:

```json
{"schema": "facturatie"}
```

Notes:

- local development can run on SQLite by leaving `POSTGRES_*` unset
- production should use PostgreSQL
- SQL Server access requires network/VPN access

## Data Refresh

Run a sync from `backend/`:

```bash
python manage.py sync_client_data --client <slug>
```

Example:

```bash
python manage.py sync_client_data --client viave
```

Inspect the last sync:

```bash
python manage.py show_sync_metadata --client viave
```

Current sync behavior:

- rebuilds `current/` datasets atomically
- appends `history/` snapshots on every sync
- writes RG and VA datasets separately
- updates `manifest/current` with:
  - `stuurtabel_id`
  - `omschrijving`
  - `soortvervoer`

Open follow-up:

- static data should not create duplicate history snapshots on every run
- see [todo.md](/Users/pedroprevost/ontwikkel/factuurcontrole/todo.md)

## Dashboard And Reporting

Current dashboard behavior:

- `stuurtabel_id` selector is backed by `manifest/current`
- selector label shows:
  - `stuurtabel_id`
  - `soortvervoer`
  - `omschrijving`
- dashboard chooses RG vs VA dataset family by `soortvervoer`
- executed controls are clickable links to control detail pages

Current control report coverage:

- Control `1`: implemented
  - title: `Bestelling ook in SW?`
  - based on `resultaat_1` and `tekst_1`
- Control `8`: implemented
  - title: `Overschrijden reistijd`
  - based on `resultaat_8`, `controlewaarde_8`, `dempelwaarde_8`, and ride timing fields
- Other controls:
  - route exists
  - currently show placeholder content until implemented

Detail page layout decisions:

- full-width (`container-fluid`) layout
- smaller no-wrap table font for wide detail tables
- location codes stripped from `locatie_van` and `locatie_naar`
- date shown as `dd-mm-yyyy`
- time shown as `HH:MM`
- empty values shown blank instead of `None`

## Recent Decisions

- Added `requirements.txt` without changing dependency policy
- Added `HANDOFF.md` for context handover
- Carried `omschrijving` and `soortvervoer` from `stuurtabel2_last` into `manifest`
- Added VA sync path:
  - `gecontroleerdeVARittenDetail`
  - `va_ritten_detail`
  - `va_ritten_controls_long`
- Split analytics by run type:
  - RG uses `ritten_detail` / `routes_detail`
  - VA uses `va_ritten_detail`
- Executed controls now link to control detail routes
- Control detail pages should use fluid width by default

## Reference Inputs In Repo

Files used as business/UI references:

- [uploads/Controles Smartfact.docx](/Users/pedroprevost/ontwikkel/factuurcontrole/uploads/Controles%20Smartfact.docx)
- [uploads/control1.png](/Users/pedroprevost/ontwikkel/factuurcontrole/uploads/control1.png)
- [uploads/control8.png](/Users/pedroprevost/ontwikkel/factuurcontrole/uploads/control8.png)
