# Historical Pinnacle availability probe

This one-request diagnostic checks whether the historical NBA odds endpoint
exposes Pinnacle even when the current endpoint does not.

The default probe uses Golden State Warriors at Detroit Pistons on 2026-03-20 and requests an explicit 20:00 UTC historical snapshot. This avoids depending on the mutable archive layout of old NBA Communications release pages; the returned odds event itself supplies the matched tipoff.

The probe reports:

- whether the historical event is present;
- whether Pinnacle is present by market;
- whether ML, Spread and Total have valid paired contracts;
- the provider snapshot timestamp and age;
- Odds API quota telemetry.

The result is diagnostic only:

- `used_for_certification=false`;
- `pinnacle_replacement=false`;
- `betting_certified=false`.

The one-shot workflow is triggered by
`ops/historical-pinnacle-probe-2026-09-28.flag` and intentionally consumes one
historical Odds API request.


If the historical endpoint rejects the request, the probe records a scrubbed
provider error state instead of failing the workflow. Only the HTTP status and
whitelisted `error_code` are persisted; the API key, request query and provider
error message are never exposed.
