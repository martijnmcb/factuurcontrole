# Factuurcontrole Platform

Factuurcontrole Platform is a Django-based replacement for the current Power BI invoice-control reporting. It synchronizes SQL Server control data per client into Parquet, queries that data with DuckDB, and serves dashboards and control reports through Django templates.

## Purpose And Scope

- read invoice-control data per client from SQL Server
- sync current and history Parquet datasets
- support both:
  - `RG` via `gecontroleerdeRittenDetail` and `gecontroleerdeRoutesDetail`
  - `VA` via `gecontroleerdeVARittenDetail`
- use `stuurtabel2_last` as the current-run source of truth
- filter dashboard/reporting by `stuurtabel_id`
- show executed controls from `controle` + `controleDone`
- reproduce Power BI control reports with a better UI

Still open:

- per-control business logic is not final for all controls
- history deduplication is not implemented yet
- multi-client loading differences still need hardening

## Architecture

```text
SQL Server (schema facturatie by default)
    -> sync_pipeline/
    -> Parquet in data/client=<slug>/
    -> DuckDB analytics in backend/apps/analytics/services.py
    -> Django views/templates in backend/apps/dashboards/
```

Main datasets:

- `manifest`
- `ritten_detail`
- `routes_detail`
- `va_ritten_detail`
- `executed_controls`
- `ritten_controls_long`
- `routes_controls_long`
- `va_ritten_controls_long`

## Exact Stack / Versions

- Python `3.13.5`
- Django `5.2.12`
- duckdb `1.5.0`
- pandas `3.0.1`
- pyarrow `23.0.1`
- pyodbc `5.3.0`
- python-dotenv `1.2.2`
- psycopg `3.3.3`
- Local environment style: `.venv` created with `python -m venv .venv`
- Confirmed SQL Server ODBC driver on this machine: `ODBC Driver 17 for SQL Server`

## Repo Layout

```text
backend/           Django project, apps, admin, management commands
sync_pipeline/     SQL Server extraction and Parquet sync pipeline
templates/         Django templates
static/            Static assets
data/              Local Parquet datasets + analytics.duckdb
uploads/           Power BI screenshots and business reference files
todo.md            Open follow-up items
HANDOFF.md         Fresh-session handover file
```

## Install And Start

Use the existing `.venv` style. Do not introduce Poetry/Conda unless explicitly requested.

1. Create and activate the virtualenv:

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

4. Minimum local `.env`:

   ```env
   DEBUG=True
   SECRET_KEY=change-me
   ALLOWED_HOSTS=127.0.0.1,localhost
   CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8081,http://localhost:8081
   ```

   If Django is behind a reverse proxy such as nginx on another local origin or port, add that full origin with scheme to `CSRF_TRUSTED_ORIGINS`.

5. Run migrations:

   ```bash
   cd backend
   python manage.py migrate
   ```

6. Create an admin user:

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

## Seed / Initial Configuration

There is no dedicated seed command yet. Initial setup is done in Django admin.

Create:

1. `Client`
2. `DataSourceConfig`
3. `SyncConfig`
4. `ClientAccess`

Current default source behavior:

- new `DataSourceConfig.extra_params` defaults to:

  ```json
  {"schema": "facturatie"}
  ```

- runtime also falls back to `facturatie` if `extra_params` is empty

Use the client slug for sync commands, for example `viave` or `Odion` depending on how the client was stored.

## Data Refresh

Run from `backend/`:

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
- appends `history/` snapshots every sync
- writes RG and VA datasets separately
- writes `manifest/current` with:
  - `stuurtabel_id`
  - `omschrijving`
  - `soortvervoer`

## Dashboard / Reporting

Dashboard behavior:

- `stuurtabel_id` selector comes from `manifest/current`
- selector label shows:
  - `stuurtabel_id`
  - `soortvervoer`
  - `omschrijving`
- executed controls link directly to control pages
- dashboard export button creates one XLSX workbook:
  - sheet 1 `summary`
  - one sheet per executed control: `control.<number>`

Detail page defaults:

- full-width layout
- compact no-wrap tables
- dates shown as `dd-mm-yyyy`
- times shown as `HH:mm`
- empty values shown blank

Client-side sorting:

- click header to sort
- `Shift+click` for multi-column sorting

## Implemented Reports

Custom report pages:

- control `1`
- control `8`
- control `10`
- control `11`
- control `1004`
- control `1005`

Generic first-pass report pages:

- `2, 3, 7, 9, 12, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24`
- `1001, 1002, 1003, 1006, 1007, 1008`

## Recent Decisions

- default SQL Server schema is now `facturatie`
- dashboard export replaced the old drilldown button
- dashboard export produces a multi-sheet XLSX workbook
- VA support added:
  - `gecontroleerdeVARittenDetail`
  - `va_ritten_detail`
  - `va_ritten_controls_long`
- dashboard/reporting switches dataset family by `soortvervoer`
- control 10 uses side-by-side maps:
  - actual route red
  - optimized route black
  - route times shown in headers
  - stop-to-stop lines kept intentionally, not turn-by-turn routing
- 1004 and 1005 redesigned as aggregate overview pages

## Current Caveats

- many control pages still need fine-tuning against Power BI
- history still grows on unchanged data
- second-client data shape still needs investigation
- dashboard XLSX export and generic client-side sorting were patched recently and should be re-verified after restart

## References

Business/UI references in repo:

- [uploads/Controles Smartfact.docx](/Users/pedroprevost/ontwikkel/factuurcontrole/uploads/Controles%20Smartfact.docx)
- Power BI screenshots in [uploads](/Users/pedroprevost/ontwikkel/factuurcontrole/uploads)

For full session continuity, also read:

- [HANDOFF.md](/Users/pedroprevost/ontwikkel/factuurcontrole/HANDOFF.md)
- [todo.md](/Users/pedroprevost/ontwikkel/factuurcontrole/todo.md)
