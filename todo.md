# TODO

- Investigate second-client data loading differences.
  Context: a second client's downloaded data looks different from the current client setup.
  Requirement: review schema, source objects, and field mappings before assuming the existing pipeline/generalized control logic fits.
  Target behavior: make data loading robust across multiple clients with client-specific or source-specific mapping where needed.

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
