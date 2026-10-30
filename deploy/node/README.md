# BARC remote node connector

Run this **on a remote Raspberry Pi**, alongside wfweb. Do not install wfweb
or this connector on the BARC CMS host. The Pi makes one outbound authenticated
WSS connection to `remote.barc.ca`; no inbound Pi ports or public radio URLs are
needed. Keep the local wfweb HTTP, WebSocket, and REST services firewalled.

1. Build/install wfweb using the repository's existing building instructions.
2. In the CMS, open **Admin → Nodes → Register a node**. Save the one-time token
   privately on the Pi. Nodes start unassigned; assign them to stations in the CMS.
3. Copy `node.env.example` to `node.env`, set its permissions to `600`, and fill
   `BARC_NODE_ID` and `BARC_NODE_TOKEN`. Set `BARC_WFWEB_URL` to the local wfweb
   frontend URL and `BARC_RADIO_WS` to its radio WebSocket URL. Use the actual ports
   configured in wfweb, and a trusted certificate/CA for HTTPS/WSS.
4. For Docker, put the CA certificate in `certs/`, set `BARC_RADIO_CA` to its
   `/certs/...` path, and run `docker compose up -d --build` from this directory.
   Host networking lets the connector reach a native wfweb on `localhost`.
   Alternatively create a Python virtualenv, install `deploy/node/requirements.txt`,
   load the private environment file, and run `python -m barc_node.agent` at repo root.

The CMS proxies frontend files over the same outbound connection and relays radio
WebSockets. Authentication and reservation permissions stay on the CMS, with a
second command/lease check on the Pi. Listener connections can receive status and
audio but cannot tune, upload microphone audio, or transmit. Expired/cancelled
reservations, role revocation, and gateway/network loss release control and PTT.
The Pi must have NTP enabled; excessive clock skew prevents operation.

Never commit `node.env`, tokens, certificates with private keys, or radio settings.
This directory contains examples only. `node.env` is ignored by Git and excluded
from the connector's Docker build context.
