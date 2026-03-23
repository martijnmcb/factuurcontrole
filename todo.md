# TODO

- Optimize sync history handling for static source data.
  Requirement: do not append a new history snapshot on every sync run when the current data has not changed.
  Target behavior: only move the previous `current` dataset into `history` when the active current dataset changes because new current data arrives.
  Notes: keep atomic rebuild of `current`, but add change detection per client/dataset so repeated syncs of identical current data do not create duplicate history snapshots.
