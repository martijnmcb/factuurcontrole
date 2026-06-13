# Security Review

## Scope
Quick review of the Django application, sync pipeline, and dashboard/reporting flows for high-value exploitable issues.

## Attack Surface Summary

### Endpoints
- `GET /` dashboard home
- `GET /clients/<slug>/` client dashboard
- `POST /clients/<slug>/refresh/` start client refresh
- `GET /clients/<slug>/refresh-status/` poll refresh status
- `GET /clients/<slug>/drilldown/`
- `GET /clients/<slug>/controls/<control_id>/`
- `GET /clients/<slug>/controls/5/route-detail/`
- `GET/POST /accounts/login/`
- `GET/POST /accounts/login/verify/`
- `POST /accounts/logout/`
- `GET /admin/`

### Auth / Session
- Django session auth
- Custom 2FA via e-mail verification code
- Role model: `admin`, `analyst`, `viewer`
- Client scoping via `ClientAccess`

### Database / Querying
- Django ORM for app data
- DuckDB for Parquet analytics
- SQL Server via `pyodbc` for sync/extract jobs

### File Handling
- Local Parquet dataset reads/writes under `data/`
- No general user upload endpoint found

### External Calls
- SMTP e-mail sending for login verification
- SQL Server connections for sync

### Config / Secrets
- Root `.env` loaded into Django settings
- SMTP, database, SQL Server, and Django secret settings come from environment

## Findings

### Fixed

1. Production could start with insecure defaults
- Risk: `DEBUG` defaulted to `True` and `SECRET_KEY` defaulted to a known placeholder.
- Impact: debug exposure, weak crypto/signing secret, unsafe production startup.
- Fix:
  - application now raises `ImproperlyConfigured` if `DEBUG=False` and `SECRET_KEY` is still the unsafe default
  - application now raises `ImproperlyConfigured` if `DEBUG=False` and `ALLOWED_HOSTS` is empty

2. Session / CSRF cookies not hardened for production
- Risk: secure cookie flags were not explicitly set.
- Impact: weaker protection if deployed over HTTPS without explicit cookie policy.
- Fix:
  - `SESSION_COOKIE_SECURE = not DEBUG`
  - `CSRF_COOKIE_SECURE = not DEBUG`
  - `SESSION_COOKIE_HTTPONLY = True`
  - `SESSION_COOKIE_SAMESITE = "Lax"`
  - `CSRF_COOKIE_SAMESITE = "Lax"`
  - added basic hardened headers/settings:
    - `SECURE_CONTENT_TYPE_NOSNIFF = True`
    - `SECURE_REFERRER_POLICY = "same-origin"`
    - `X_FRAME_OPTIONS = "DENY"`
    - `SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"`
    - configurable HSTS / SSL redirect settings

### Reviewed, no immediate exploitable issue found

1. Authorization / access control
- Client access is enforced server-side via `ClientContextMixin.get_client()`.
- Dashboard, drilldown, control, and refresh endpoints all resolve the client through the authenticated user’s allowed clients.
- No direct IDOR found in the reviewed routes.

2. SQL injection
- SQL Server extractor uses parameter binding at the cursor layer where values are dynamic.
- DuckDB analytics contains many f-string queries, but the interpolated values reviewed are:
  - server-side dataset paths
  - integer `stuurtabel_id` / `control_id`
  - fixed internal SQL fragments
- No direct user-controlled string interpolation into SQL was identified in the reviewed paths.

3. File handling
- No public upload handler found.
- Parquet paths are server-controlled and derived from internal client slugs / dataset names.
- No obvious path traversal sink exposed to end users was found in the reviewed routes.

4. SSRF
- No user-controlled outbound HTTP requests found.
- External integrations are SMTP and SQL Server only.

## Residual Risks / Follow-up

1. Dependencies are version-ranged, not pinned
- `Django`, `duckdb`, `pandas`, `pyarrow`, `pyodbc`, `python-dotenv`, `psycopg[binary]` are constrained but not locked.
- Recommendation: use a lockfile or pinned deploy artifact for production reproducibility and patch management.

2. Debug should remain explicitly disabled in production
- Current code is now safer, but production still depends on `.env` discipline.

3. Analytics SQL should remain server-composed only
- Current dynamic DuckDB SQL appears safe because user input is normalized to integers or internal enums.
- Keep it that way; do not interpolate raw request strings into query fragments later.
