# HANDOFF

This file is for a fresh agent instance with no prior conversation context.

## Current Status

This repo is a Django + DuckDB + Parquet invoice-control platform replacing Power BI dashboards.

The active work is no longer scaffolding. The active work is:

- sync SQL Server control data per client into Parquet
- reproduce Power BI control reports in Django
- keep business outcomes aligned with Power BI
- improve UI/UX relative to Power BI

The app is running, `viave` sync works, VA and RG are both supported, and multiple control pages are already implemented.

## Exact Environment

Use the existing `.venv`. Do not create a second env unless the user explicitly asks.

- Repo: `/Users/pedroprevost/ontwikkel/factuurcontrole`
- Virtualenv: `/Users/pedroprevost/ontwikkel/factuurcontrole/.venv`
- Python: `3.13.5`
- Django: `5.2.12`
- duckdb: `1.5.0`
- pandas: `3.0.1`
- pyarrow: `23.0.1`
- pyodbc: `5.3.0`
- python-dotenv: `1.2.2`
- psycopg: `3.3.3`
- Install mode used here: `.venv` + `requirements.txt` or editable install
- Confirmed local SQL Server ODBC driver: `ODBC Driver 17 for SQL Server`

Important:

- avoid Conda/Poetry duplicate envs
- use `.venv/bin/python` or activate `.venv`
- current docs assume `python -m venv .venv`

## Source / Schema Contracts

Default SQL Server schema is now `facturatie`.

This was implemented in:

- [backend/apps/clients/models.py](/Users/pedroprevost/ontwikkel/factuurcontrole/backend/apps/clients/models.py)
- [sync_pipeline/sqlserver/extractor.py](/Users/pedroprevost/ontwikkel/factuurcontrole/sync_pipeline/sqlserver/extractor.py)
- [backend/apps/clients/migrations/0002_default_facturatie_schema.py](/Users/pedroprevost/ontwikkel/factuurcontrole/backend/apps/clients/migrations/0002_default_facturatie_schema.py)

Meaning:

- new `DataSourceConfig.extra_params` defaults to `{"schema": "facturatie"}`
- existing empty configs also fall back to `facturatie` at runtime

Current-run source:

- `facturatie.stuurtabel2_last`
- used fields:
  - `id` -> `stuurtabel_id`
  - `omschrijving`
  - `soortvervoer`

Run type rule:

- `RG` -> use `gecontroleerdeRittenDetail` + `gecontroleerdeRoutesDetail`
- `VA` -> use `gecontroleerdeVARittenDetail`

Control metadata:

- `facturatie.controle`
- `omschrijving` is used for executed-control display

## Dataset Contracts

Parquet root:

- `data/client=<slug>/dataset=<dataset>/...`

Main datasets:

- `manifest`
- `ritten_detail`
- `routes_detail`
- `va_ritten_detail`
- `executed_controls`
- `ritten_controls_long`
- `routes_controls_long`
- `va_ritten_controls_long`

Manifest current contains:

- `stuurtabel_id`
- `omschrijving`
- `soortvervoer`
- sync metadata

Executed controls contains:

- `stuurtabel_id`
- `controle_id`
- `omschrijving`
- plus sync metadata fields

## Current Dashboard / Report Status

Main dashboard:

- selector backed by `manifest/current`
- selector label shows `stuurtabel_id`, `soortvervoer`, `omschrijving`
- executed controls are links to control pages
- dashboard export button creates one multi-sheet XLSX workbook

Dashboard workbook export:

- sheet 1: `summary`
- then one worksheet per executed control named `control.<number>`
- summary sheet columns:
  - `Control number`
  - `Control name`
  - `Total checked`
  - `Total deviations`
  - `Deviation %`

Important very recent fix:

- dashboard export had stale unpacking for control 10 after route-duration work
- both stale unpack sites in [backend/apps/dashboards/views.py](/Users/pedroprevost/ontwikkel/factuurcontrole/backend/apps/dashboards/views.py) were patched
- `python backend/manage.py check` passes
- user still needs to re-try the dashboard XLSX export after restart to confirm no more control-specific bundle mismatches remain

Per-control export:

- CSV and XLSX export buttons exist on control pages

Pagination:

- `100` rows/page on report detail tables
- generic control pages paginated
- control 1 paginated
- control 8 paginated
- control 10 route detail paginated
- control 11 vehicle table paginated
- drilldown paginated
- control 1004 / 1005 custom aggregate pages intentionally not paginated

Global formatting:

- dates `dd-mm-yyyy`
- times `HH:mm`
- blank values instead of `None`

## Implemented Control Pages

Custom pages:

- Control `1`
- Control `8`
- Control `10`
- Control `11`
- Control `1004`
- Control `1005`

Generic first-pass pages exist for:

- `2, 3, 7, 9, 12, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24`
- `1001, 1002, 1003, 1006, 1007, 1008`

Control-specific decisions already applied:

- Control 1:
  - `Routenummer` label fixed
  - `Perceelvervoerder` added
- Control 3:
  - exact route columns set to user spec
- Control 7:
  - exact columns set to `Datum, Routenummer, Kenteken, Routedetail, Voertuigtype`
  - reads route dataset so kenteken values are correct
- Control 10:
  - route selector only shows gain routes
  - route selector key includes date + route number
  - actual route line red
  - optimized route line black
  - mouse-wheel zoom enabled
  - route durations shown in map headers
  - auto-apply route dropdown
  - route detail table below maps
  - client-side multi-column sorting requested and applied
- Control 11:
  - `resultaat_11` rule:
    - `0` or `1` is OK
    - `>1` is deviation
- Control 14:
  - `Resultaat` removed from frontend
- Control 15:
  - exact reduced columns set
- Control 16, 17, 22:
  - `Resultaat` removed from frontend
- Control 1004:
  - redesigned aggregate emission page
  - summary tables include rows with `resultaat_1004 = 0`
  - header text now `Afgelegde reizigers kilometers per emissieniveau`
- Control 1005:
  - redesigned aggregate fuel page similar to 1004

## Sorting Status

Shared client-side sorting was implemented in:

- [static/js/dashboard.js](/Users/pedroprevost/ontwikkel/factuurcontrole/static/js/dashboard.js)
- [templates/base.html](/Users/pedroprevost/ontwikkel/factuurcontrole/templates/base.html)

Behavior:

- click header to sort
- `Shift+click` for multi-column sorting
- applies to `table.report-table, table.sortable-table`

Very recent sorting fix:

- browser cache was likely serving old JS
- base template now loads `dashboard.js` with `?v=20260323-1`
- base template also calls `window.initReportTableSorting()` as fallback
- `dashboard.js` now exposes `initReportTableSorting()` globally and guards against double init

User needs to verify after restart that control 1 sorting now works visibly.

## Control 10 Map Context

Map route logic is based on RG `gecontroleerdeRittenDetail` fields:

- actual order:
  - `netto_instap`
  - `netto_uitstap`
- replanned order:
  - `netto_herplan_instap`
  - `netto_herplan_uitstap`
- coordinates:
  - `latitude_van`
  - `longitude_van`
  - `latitude_naar`
  - `longitude_naar`

Map currently uses stop-to-stop line segments, not road-snapped turn-by-turn routing. User explicitly chose to leave it that way for now.

## Recent Verification

Recent checks that passed:

- `python backend/manage.py check`

This passed after:

- sorting bootstrap changes
- dashboard export bundle fixes
- default `facturatie` schema changes

Known live runtime item still pending manual verification:

- dashboard XLSX export from `/clients/viave/?stuurtabel_id=352&export=xlsx`

The code was patched for control 10 unpacking, but the user had not yet confirmed the final retry before restarting.

## Important Paths

Docs:

- [README.md](/Users/pedroprevost/ontwikkel/factuurcontrole/README.md)
- [HANDOFF.md](/Users/pedroprevost/ontwikkel/factuurcontrole/HANDOFF.md)
- [todo.md](/Users/pedroprevost/ontwikkel/factuurcontrole/todo.md)

Core analytics / views:

- [backend/apps/analytics/services.py](/Users/pedroprevost/ontwikkel/factuurcontrole/backend/apps/analytics/services.py)
- [backend/apps/dashboards/views.py](/Users/pedroprevost/ontwikkel/factuurcontrole/backend/apps/dashboards/views.py)
- [backend/apps/dashboards/urls.py](/Users/pedroprevost/ontwikkel/factuurcontrole/backend/apps/dashboards/urls.py)

Templates / UI:

- [templates/base.html](/Users/pedroprevost/ontwikkel/factuurcontrole/templates/base.html)
- [templates/dashboards/client_dashboard.html](/Users/pedroprevost/ontwikkel/factuurcontrole/templates/dashboards/client_dashboard.html)
- [templates/dashboards/control_1_report.html](/Users/pedroprevost/ontwikkel/factuurcontrole/templates/dashboards/control_1_report.html)
- [templates/dashboards/control_10_report.html](/Users/pedroprevost/ontwikkel/factuurcontrole/templates/dashboards/control_10_report.html)
- [templates/dashboards/control_11_report.html](/Users/pedroprevost/ontwikkel/factuurcontrole/templates/dashboards/control_11_report.html)
- [templates/dashboards/control_1004_report.html](/Users/pedroprevost/ontwikkel/factuurcontrole/templates/dashboards/control_1004_report.html)
- [templates/dashboards/control_1005_report.html](/Users/pedroprevost/ontwikkel/factuurcontrole/templates/dashboards/control_1005_report.html)
- [templates/dashboards/drilldown.html](/Users/pedroprevost/ontwikkel/factuurcontrole/templates/dashboards/drilldown.html)
- [static/js/dashboard.js](/Users/pedroprevost/ontwikkel/factuurcontrole/static/js/dashboard.js)
- [static/css/app.css](/Users/pedroprevost/ontwikkel/factuurcontrole/static/css/app.css)

Pipeline:

- [sync_pipeline/sqlserver/extractor.py](/Users/pedroprevost/ontwikkel/factuurcontrole/sync_pipeline/sqlserver/extractor.py)
- [sync_pipeline/jobs/sync_client.py](/Users/pedroprevost/ontwikkel/factuurcontrole/sync_pipeline/jobs/sync_client.py)
- [sync_pipeline/parquet/manifest.py](/Users/pedroprevost/ontwikkel/factuurcontrole/sync_pipeline/parquet/manifest.py)

## Open Challenges

1. Per-control business logic is still incomplete.
   Many controls still use first-pass generic logic and need Power BI parity tuning.

2. History handling is still naive.
   Static current data still appends duplicate history snapshots.

3. Multi-client loading is not hardened yet.
   A second client looks structurally different and needs mapping review.

4. Dashboard XLSX export needs one manual re-test after the latest code patch.

5. Client-side sorting needs one manual re-test after the cache-busting/fallback init fix.

## Best Next Steps

After restart, the best first checks are:

1. Re-open control 1 and verify header sorting works.
2. Re-run dashboard XLSX export for `viave` and confirm the workbook downloads correctly.
3. If both are stable, continue fine-tuning control reports against the uploaded Power BI screenshots.
4. Then return to the second-client loading differences and history dedup logic.
