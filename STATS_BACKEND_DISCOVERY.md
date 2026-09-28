# NBA Stats backend discovery

The hosted runner can reach public `www.nba.com/stats` pages while direct
`stats.nba.com/stats/*` requests time out. This diagnostic inspects the public
frontend bundles to identify which official backend hosts/endpoints the current
NBA Stats site references.

It persists only:

- public script URLs without query strings;
- byte counts and SHA-256 hashes;
- counts of whitelisted endpoint markers;
- backend and endpoint hint names.

It never persists JavaScript source, credentials or basketball data and is
always `NETWORK_DIAGNOSTIC_ONLY`.

A discovered string is not provider approval. Any candidate route must be
tested independently for schema, PIT behavior, data parity and prospective
reliability before it can be considered for a provider adapter.
