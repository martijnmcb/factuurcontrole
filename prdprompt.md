# Codex Project Prompt
# Factuurcontrole Dashboard Platform

You are a senior software architect and Python engineer.

Your task is to generate a full project scaffold for a production-ready MVP web application.

The project name is:

Factuurcontrole Platform

The system replaces Power BI dashboards for invoice control results.

The codebase must be clean, maintainable, modular and suitable for long term development.

Development must work with Python virtual environments. Docker must NOT be used.

------------------------------------------------------------

# 1. Product Overview

The application must:

- read invoice control result data from multiple SQL Server customer databases
- synchronize those results into Parquet datasets
- use DuckDB for analytics queries
- provide dashboards via a Django web application
- allow user access per client/opdrachtgever

Each client has its own SQL Server database.

Cross-client reporting is NOT required.

------------------------------------------------------------

# 2. Important Business Rules

1. Each client has its own SQL Server database.
2. A factuur/invoice can be processed multiple times.
3. Only the latest version is relevant.
4. The latest version is determined using:

stuurtabel2_last

5. Source data objects are:

stuurtabel2_last  
gecontroleerdeRittenDetail  
gecontroleerdeRoutesDetail  
controle  
controleDone  

6. The table `controleDone` indicates which controls were executed for a given `stuurtabel_id`.

7. Different clients may use different controls.

8. Controls may change over time.

9. Dashboards must dynamically adapt to the controls executed for the current dataset.

------------------------------------------------------------

# 3. Technology Stack

Backend

Python 3.13  
Django  
DuckDB  
pyodbc  
pandas  

Storage

Parquet

Application database

PostgreSQL

Frontend

Django templates  
Chart.js  
Bootstrap  

Development

Python virtualenv (venv)

------------------------------------------------------------

# 4. System Architecture

SQL Server (per client)
↓
sync pipeline (Python)
↓
Parquet datasets
↓
DuckDB analytics
↓
Django webapp
↓
Dashboards

------------------------------------------------------------

# 5. Repository Structure

Generate the project with this structure.

factuurcontrole-platform/

README.md  
pyproject.toml  
.env.example  

backend/

    manage.py

    config/
        settings.py
        urls.py
        asgi.py
        wsgi.py

    apps/

        core/
        accounts/
        clients/
        sync_jobs/
        analytics/
        dashboards/

templates/
static/

sync_pipeline/

    sqlserver/
        connection.py
        extractor.py

    parquet/
        writer.py
        datasets.py
        manifest.py

    jobs/
        sync_client.py

analytics/
    duckdb_queries.sql

data/
scripts/

------------------------------------------------------------

# 6. Django Apps

Generate these Django apps.

core  
shared utilities

accounts  
user management

roles  
Admin  
Analyst  
Viewer

clients  
models:

Client  
ClientAccess  
DataSourceConfig  
SyncConfig  

sync_jobs  
models:

SyncRun  

services for sync orchestration

analytics  
DuckDB connection layer

dashboards  
dashboard views  
chart endpoints  
drilldown tables  

------------------------------------------------------------

# 7. Data Synchronisation

For each client:

1 read stuurtabel2_last  
2 determine current stuurtabel_id values  
3 extract data from  

gecontroleerdeRittenDetail  
gecontroleerdeRoutesDetail  
controle  
controleDone  

4 write Parquet datasets  
5 update manifest dataset  

------------------------------------------------------------

# 8. Parquet Storage

Structure

data/

client=<slug>/

dataset=ritten_detail/
current/
history/

dataset=routes_detail/
current/
history/

dataset=executed_controls/
current/
history/

dataset=manifest/
current/

Current dataset

contains only latest records.

History dataset

append-only.

------------------------------------------------------------

# 9. Data Models

ritten_detail

fields

client_slug  
stuurtabel_id  
rit_id  
vervoerder  
perceel  
ritdatum  
controlecode  
controle_uitkomst  
afwijkingsbedrag  
synced_at  

routes_detail

fields

client_slug  
stuurtabel_id  
route_id  
vervoerder  
perceel  
controlecode  
controle_uitkomst  
afwijkingsbedrag  
synced_at  

executed_controls

source

controle  
controleDone  

fields

client_slug  
stuurtabel_id  
controlecode  
uitgevoerd  
timestamp  

manifest

fields

client_slug  
stuurtabel_id  
is_current  
sync_timestamp  

------------------------------------------------------------

# 10. Analytics Layer

Use DuckDB to query Parquet.

Example queries

SELECT COUNT(*) FROM ritten_detail

SELECT controlecode, COUNT(*)
FROM ritten_detail
GROUP BY controlecode

------------------------------------------------------------

# 11. Dashboards

Implement pages

dashboard home

list accessible clients

client dashboard

show

KPI cards

total checked  
total deviations  
deviation percentage  
deviation amount  

charts

deviations per control  
deviations per vervoerder  
trend over time  

drilldown page

table with filters

------------------------------------------------------------

# 12. Dynamic Controls

Dashboards must only show controls executed for the selected dataset.

Use controleDone.

Example

stuurtabel_id 456

controls executed

1  
2  
8  
9  
19  

Only these controls should appear in dashboards.

------------------------------------------------------------

# 13. Security

Requirements

login required  
users only see assigned clients  
permission checks in dashboard views  
secrets never exposed  

------------------------------------------------------------

# 14. Admin

Django admin must manage

clients  
datasource configs  
sync configs  
client access  
sync runs  

------------------------------------------------------------

# 15. Management Commands

Implement command

python manage.py sync_client_data --client <slug>

This command must

extract SQL Server data  
write Parquet datasets  
update manifest  
log results  

------------------------------------------------------------

# 16. Development Setup

The project must run locally using

python -m venv .venv  
source .venv/bin/activate  
pip install -e .  

Run server

python manage.py runserver

------------------------------------------------------------

# 17. Code Quality

Ensure

modular architecture  
service layers  
type hints where reasonable  
clear docstrings  
structured logging  
environment based settings  

Avoid

business logic in templates  
monolithic views  
hardcoded paths  

------------------------------------------------------------

# 18. Deliverables

Generate a complete working scaffold including

Django project  
models  
admin  
services  
sync pipeline  
analytics layer  
dashboard pages  
README  
.env.example  
initial migrations  

Where database schema details are unknown

add clear TODO markers.

The project must start locally and show a working dashboard skeleton.