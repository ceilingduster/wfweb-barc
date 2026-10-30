# Call-home API v1

Base URL: `https://remote.barc.ca`. Discover endpoints with `GET /api/nodes`.
First boot needs **no pre-issued credential, OAuth login, or administrator action**.
Every new node is unassigned. Station assignments and radio access remain admin-
and reservation-controlled.

## Register

`POST /api/nodes/register` with `Content-Type: application/json`:

```json
{
  "name": "Club Raspberry Pi",
  "status": "starting",
  "wfweb_url": "https://localhost:8080/",
  "info": {
    "hostname": "club-pi",
    "model": "Raspberry Pi 5",
    "os": "Linux",
    "architecture": "aarch64",
    "agent_version": "1.0.0",
    "uptime_seconds": 30
  }
}
```

Returns `201` with `node` (including its unique `id`), a one-time `node_token`,
`relay_url`, `heartbeat_interval: 15`, and `offline_after: 45`. Store the token
privately. The server stores only its SHA-256 hash; it cannot recover a lost token.

For reliable first boot, the supplied connector generates and saves its own
`node_id` (`node-` followed by a UUID's 32 lowercase hex digits) and a random
URL-safe `node_token` **before** contacting the API. It supplies both fields in
the registration body. No pre-existing authorization header is needed. Retrying
with the same pair returns `200`, preserves station assignments, and never creates
a duplicate. An incorrect token for a claimed ID returns `409`. When the caller
provides the token, the API does not echo it back.

## Retrieve identity and information

`GET /api/nodes/me` with `Authorization: Bearer NODE_TOKEN` returns that node's
identity, information, current assignments, and status. `GET /api/nodes/NODE_ID`
does the same, but requires the credential for that exact node. There is no public
node listing and no way to obtain another node's credential.

## Update information

`PATCH /api/nodes/NODE_ID` with the same bearer header and a JSON body containing
any of `name`, `status`, `wfweb_url`, or `info`. `info` replaces the metadata object.
Status values: `starting`, `ready`, `degraded`, `offline`. Names have at most 120
characters, URLs at most 500, metadata at most 8 KiB, and requests at most 16 KiB.
URLs must be HTTP(S) and cannot contain credentials, query strings, or fragments.
Only administrators can change station assignments; identity and permissions are
not writable through the node API.

## Heartbeat

`POST /api/nodes/NODE_ID/heartbeat` with the bearer header and JSON:

```json
{"status":"ready","info":{"hostname":"club-pi","uptime_seconds":120}}
```

An empty JSON object is also valid. Send a heartbeat every 15 seconds. The CMS uses
server timestamps and marks API-only nodes offline after 45 seconds without contact.
`online` means the node is calling home or has a live relay; `relay_connected` means
its console tunnel is connected. An HTTP heartbeat never grants radio permissions
or makes a disconnected console available. `reported_status` is advisory telemetry.
The response also includes `created_at`, `last_seen`, `last_heartbeat`, `stations`,
and `assignment_status` (`unassigned` or `assigned`). Timestamps are Unix seconds.

## Responses and limits

- `200`: retrieved, updated, or already registered with the same identity.
- `201`: new node registered.
- `400`: invalid JSON, identity, metadata, or fields.
- `401`: missing/incorrect node credential for reads or updates.
- `409`: the proposed identity belongs to another credential.
- `413`: request too large.
- `429`: new registration limit reached; follow `Retry-After`.

New registrations are limited to 20 per connecting peer per hour and 100 globally
per hour. Retries for an existing correct identity do not consume that limit.
Behind an origin tunnel, nodes can share the same connecting-peer limit. Identity
files are mode `0600`, outside Git and outside Docker build contexts. HTTPS is
required by the production connector. Bearer credentials are never accepted in URL
query parameters, and API responses are not cached.
