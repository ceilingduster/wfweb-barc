# BARC remote node connector

Run this **on a remote Raspberry Pi**, alongside wfweb. Do not install wfweb
or this connector on the BARC CMS host. The Pi makes one outbound authenticated
WSS connection to `remote.barc.ca`; no inbound Pi ports or public radio URLs are
needed. Keep the local wfweb HTTP, WebSocket, and REST services firewalled.

1. Build/install wfweb using the repository's existing building instructions.
2. In `wfweb-barc/deploy/node/` (the directory containing `compose.yaml`), copy
   `node.env.example` to **`.env`** and run `chmod 600 .env`. Paste the complete
   contents of this Pi's wfweb `server.crt` into the quoted `BARC_RADIO_CA` value,
   including its BEGIN/END lines. Paste the certificate text, not a filename;
   never include a private key. No node ID or token is needed for automatic
   registration. For a manually registered node, paste its ID and token here too.
3. Run `docker compose up -d --build` from that same `deploy/node/` directory.
   The connector defaults to `https://localhost:8080/` for HTTP and
   `wss://localhost:8080` for radio WebSockets. The outbound tunnel identifies
   the remote Pi; it does not discover a custom local wfweb port. Set the optional
   URL overrides only for a different local address/port. Host networking reaches
   native wfweb on `localhost`. The `node-state` volume preserves the identity.
4. Alternatively, install `deploy/node/requirements.txt` in a Python virtualenv,
   export the variables from the private `.env` file, and run `python -m barc_node.agent` at repo
   root. Identity is saved in `~/.local/state/barc-node/identity.json`, or the
   `BARC_NODE_STATE` path. State files are owner-only and contain the node's key.
5. On first boot the connector generates and persists a unique UUID and random
   credential, then registers without prior authentication. It reports node
   information and status every 15 seconds. In **Admin → Nodes**, find the new
   unassigned Pi and associate it with its stations. No station or user access
   is granted automatically.

See [API.md](API.md) for registration, identity retrieval, metadata updates, and
heartbeats. Existing manually pre-provisioned nodes can still set both
`BARC_NODE_ID` and `BARC_NODE_TOKEN`. Do not clone a populated identity/state volume
between Pis; each installation must generate its own identity.

The CMS proxies frontend files over the same outbound connection and relays radio
WebSockets. Authentication and reservation permissions stay on the CMS, with a
second command/lease check on the Pi. Listener connections can receive status and
audio but cannot tune, upload microphone audio, or transmit. Expired/cancelled
reservations, role revocation, and gateway/network loss release control and PTT.
The Pi must have NTP enabled; excessive clock skew prevents operation.

Never commit `.env`, tokens, certificates with private keys, or radio settings.
This directory contains examples only. `.env` is ignored by Git and excluded
from the connector's Docker build context.
