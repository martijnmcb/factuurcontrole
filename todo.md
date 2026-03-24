# TODO

- Optimize sync history handling for static source data.
  Requirement: do not append a new history snapshot on every sync run when the current data has not changed.
  Target behavior: only move the previous `current` dataset into `history` when the active current dataset changes because new current data arrives.
  Notes: keep atomic rebuild of `current`, but add change detection per client/dataset so repeated syncs of identical current data do not create duplicate history snapshots.

- Investigate second-client data loading differences.
  Context: a second client's downloaded data looks different from the current client setup.
  Requirement: review schema, source objects, and field mappings before assuming the existing pipeline/generalized control logic fits.
  Target behavior: make data loading robust across multiple clients with client-specific or source-specific mapping where needed.

- Re-verify recent UI/runtime fixes after restart.
  Context: two very recent fixes were applied just before restart.
  Items to verify:
  - client-side table sorting works on control pages such as control 1
  - dashboard multi-sheet XLSX export works from `/clients/<slug>/?stuurtabel_id=<id>&export=xlsx`
  Notes: code was patched for static JS cache busting and control 10 export bundle unpacking, but both still need a manual browser retry after restart.

- Continue Power BI parity tuning per control.
  Context: several controls are implemented as first-pass pages and still need field/layout/business-logic refinement.
  Priority controls already actively refined:
  - `1`
  - `3`
  - `7`
  - `8`
  - `10`
  - `11`
  - `14`
  - `15`
  - `16`
  - `17`
  - `22`
  - `1004`
  - `1005`
  Requirement: compare each page with uploaded Power BI screenshots and correct KPI rules, columns, labels, and grouping where needed.
