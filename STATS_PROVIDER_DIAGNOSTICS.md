# NBA stats provider diagnostics

The canonical production stats path remains `stats.nba.com`. Hosted runners
currently time out on the LeagueDash endpoints, so Pulsar keeps all alternate
route investigation isolated from predictive authority.

## Frontend backend discovery

`nba.stats_backend_probe` reads the public NBA Stats HTML and loaded
JavaScript bundles and persists only hashes, sizes, marker counts, sanitized
backend host/path hints, and route candidates. It never stores source code,
query strings, cookies or tokens.

The current frontend references both `stats.nba.com` and
`api-hub.nba.com`. The visible api-hub routes are primarily authentication
routes, while `leaguedashteamstats` remains referenced separately.

## Official route transport probe

`nba.stats_route_transport_probe` tests only three allowlisted official NBA
routes with the same minimal LeagueDashTeamStats query:

- `https://stats.nba.com/stats/leaguedashteamstats`
- `https://api-hub.nba.com/stats/leaguedashteamstats`
- `https://api-hub.nba.com/leaguedashteamstats`

It records only transport/result metadata and validates a response as an NBA
stats payload only when it contains at least 25 team rows.

A successful alternate route would still remain diagnostic. The probe always
sets `predictive_evidence_eligible=false` and
`production_provider_authorized=false`; provider promotion would require a
separate frozen adapter, parity review and fresh prospective validation.
