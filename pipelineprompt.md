# Codex Pipeline Prompt
# SQL Server → Parquet Sync Pipeline

You are a senior Python data engineer.

Extend the existing Factuurcontrole Platform project by implementing the full data ingestion pipeline that synchronizes SQL Server data into Parquet datasets.

The code must integrate with the project created from prdprompt.md.

The goal is to build a robust, maintainable pipeline that:

- extracts invoice control data from SQL Server
- determines the latest processed invoice versions
- writes structured Parquet datasets
- maintains current and history datasets
- enables DuckDB analytics queries

The pipeline must run as part of the Django project but remain logically separated in the `sync_pipeline` module.

------------------------------------------------------------

# 1. Pipeline Responsibilities

The pipeline must:

1. connect to the SQL Server database for a specific client
2. read the list of active invoice runs from:

stuurtabel2_last

3. extract data for those runs from:

gecontroleerdeRittenDetail  
gecontroleerdeRoutesDetail  
controle  
controleDone  

4. write structured Parquet datasets

5. rebuild the `current` dataset for that client

6. append new records to the `history` dataset

7. update the `manifest` dataset

------------------------------------------------------------

# 2. Source Database Logic

The pipeline must support multiple clients.

Each client has its own SQL Server connection configuration stored in the Django model:

DataSourceConfig

Fields include:

- host
- database
- username
- password
- driver

------------------------------------------------------------

# 3. Extract Phase

Implement extractor services that:

connect to SQL Server using pyodbc.

Extract the following dataframes.

------------------------------------------------------------

## Current invoice runs

Query:

stuurtabel2_last

Return:

stuurtabel_id

------------------------------------------------------------

## Ritten detail

Source:

gecontroleerdeRittenDetail

Filter:

stuurtabel_id IN current_ids

------------------------------------------------------------

## Routes detail

Source:

gecontroleerdeRoutesDetail

Filter:

stuurtabel_id IN current_ids

------------------------------------------------------------

## Controls

Source tables:

controle  
controleDone  

Filter:

stuurtabel_id IN current_ids

------------------------------------------------------------

# 4. Data Normalization

Before writing to Parquet:

- convert column names to snake_case
- add metadata columns:

client_slug  
stuurtabel_id  
synced_at  

Ensure consistent schemas even if some columns are missing.

------------------------------------------------------------

# 5. Parquet Dataset Layout

Use this structure.

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

------------------------------------------------------------

# 6. Current Dataset

The current dataset must contain only records belonging to the active `stuurtabel_id` values.

Strategy:

- rebuild the entire current dataset for a client on each sync
- write to a temporary folder
- replace the existing current folder atomically

------------------------------------------------------------

# 7. History Dataset

History must be append-only.

Structure:

history/
year=<YYYY>/
month=<MM>/
stuurtabel_id=<id>/

Write one Parquet file per sync run.

------------------------------------------------------------

# 8. Manifest Dataset

The manifest dataset must store:

client_slug  
stuurtabel_id  
is_current  
sync_timestamp  

This dataset allows analytics queries to know which runs are current.

------------------------------------------------------------

# 9. Pipeline Structure

Implement modules:

sync_pipeline/

sqlserver/

connection.py
create_connection(config)

extractor.py
functions:

extract_current_runs()  
extract_ritten_detail()  
extract_routes_detail()  
extract_controls()  

------------------------------------------------------------

parquet/

writer.py
write_parquet(df, path)

datasets.py
write_current_dataset()
append_history_dataset()

manifest.py
update_manifest()

------------------------------------------------------------

jobs/

sync_client.py

main orchestration function:

sync_client(client_slug)

Steps:

1 load datasource config
2 connect to SQL Server
3 extract current IDs
4 extract datasets
5 normalize data
6 write history datasets
7 rebuild current datasets
8 update manifest
9 log sync run

------------------------------------------------------------

# 10. Django Integration

Expose the pipeline via management command:

python manage.py sync_client_data --client <slug>

The command must:

- call the pipeline job
- log SyncRun records
- handle errors gracefully

------------------------------------------------------------

# 11. Performance Considerations

Use pandas for intermediate transformations.

Write Parquet using pyarrow.

Ensure:

- files are reasonably sized
- avoid writing thousands of tiny files
- reuse DuckDB connections where possible

------------------------------------------------------------

# 12. Error Handling

Pipeline must handle:

- SQL connection errors
- schema mismatch
- empty result sets
- partial failures

Log errors in SyncRun.

------------------------------------------------------------

# 13. Logging

Log:

- number of rows extracted
- number of rows written
- execution time
- client name
- stuurtabel_ids processed

------------------------------------------------------------

# 14. Developer Experience

Provide scripts:

scripts/run_sync.py

Example:

python scripts/run_sync.py --client altena

------------------------------------------------------------

# 15. Code Quality

Use:

- type hints
- docstrings
- structured logging
- clear function boundaries

Avoid:

- SQL embedded in many places
- business logic in views
- tight coupling between Django and pipeline code

------------------------------------------------------------

# 16. Deliverables

Generate:

- extractor services
- parquet writers
- sync orchestration
- Django management command
- documentation in README

Add TODO markers where SQL schema assumptions are uncertain.

Ensure the pipeline runs locally even without a real SQL Server by allowing mocked data.