# Incoming Request Capture (Operator Procedure)

> **Status:** Current operator runbook
> **Safety:** Full-content capture is a bounded, human-authorized diagnostic
> exception. Use the smallest count/TTL that answers the question, capture
> only from traffic you are authorized to inspect, and stop/clean up the
> exact session artifacts when finished.

The request-capture facility (default **OFF**) lets an operator capture the
full original incoming bytes of a finite number of matching requests, with
known incoming authentication values masked, into a local `0700` directory
shared by the API workers. It changes nothing about auth, validation,
admission, accounting, or forwarding, and it adds no database state.

## What You Need

- The exact deployed commit (this becomes `REQUEST_CAPTURE_DEPLOYED_REVISION`;
  the facility never guesses it from a checkout).
- A dedicated host directory for captures, e.g. `/var/lib/slaif-capture`.
  Keep it **outside the checkout and outside any database directory**.
- The production Compose stack (`docker-compose.production.yml`). The api
  service declares only explicit `environment` entries (no `env_file`) and
  loads secrets through `_FILE` variables via the entrypoint
  `/usr/local/bin/load-production-secrets`, so the capture settings are
  supplied with an **external overlay file** — no Dockerfile or Compose
  source edits are required.
- The gateway CLI is installed at `/usr/local/bin/slaif-gateway`. Because
  `docker compose exec` does **not** rerun the container entrypoint, every
  CLI invocation below goes through the loader explicitly. The loader loads
  the `_FILE` secrets, then drops to the `slaif` user itself. Run `exec` with
  `--user root` (the service runs as root and the secret files may require
  root); do **not** prepend `runuser`/`su`, and do **not** add a `--`
  separator after the loader — everything after the loader path is the
  command the loader executes as `slaif`.

## 1. Deploy The Exact Commit And Query The Runtime UID

After deploying the pinned commit, query the **actual** runtime UID/GID (the
image creates `slaif` as a system user, so the numbers are not fixed
constants). Use the production Compose file alone — the capture overlay does
not exist yet, and compose rejects a missing `-f` file. `-T` keeps the
output clean and noninteractive:

```bash
DC_BASE=(docker compose -f docker-compose.production.yml)

SLAIF_UID=$("${DC_BASE[@]}" exec -T --user root api id -u slaif)
SLAIF_GID=$("${DC_BASE[@]}" exec -T --user root api id -g slaif)
echo "slaif uid=$SLAIF_UID gid=$SLAIF_GID"
```

## 2. Create The External Overlay And The Dedicated 0700 Host Directory

Create the capture overlay **outside the checkout** (for example
`$HOME/slaif-capture-191/docker-compose.capture-191.yml`), substituting the
exact deployed commit and a provenance label:

```yaml
# Objective-191 operator capture overlay — apply only for the capture window.
# Bring up with:  "${DC[@]}" up -d --force-recreate api
# Remove the capture with:
#   docker compose -f docker-compose.production.yml up -d --force-recreate api
services:
  api:
    environment:
      REQUEST_CAPTURE_ENABLED: "true"
      REQUEST_CAPTURE_DIR: /var/lib/slaif-capture
      REQUEST_CAPTURE_DEPLOYED_REVISION: "<exact deployed commit>"
      REQUEST_CAPTURE_REVISION_PROVENANCE: "operator-<who/why>"
    volumes:
      # Dedicated WRITABLE bind mount; NOT the readonly profile/config mount.
      # All API workers must see the same directory: the armed window is
      # shared local-filesystem state and counts are claimed atomically
      # across every worker.
      - /var/lib/slaif-capture:/var/lib/slaif-capture
```

Define the overlay-backed compose command only now that the file exists:

```bash
CAPTURE_OVERLAY="$HOME/slaif-capture-191/docker-compose.capture-191.yml"
DC=(docker compose -f docker-compose.production.yml -f "$CAPTURE_OVERLAY")
```

Prepare the host directory with the runtime ownership:

```bash
sudo mkdir -p /var/lib/slaif-capture
sudo chown "$SLAIF_UID:$SLAIF_GID" /var/lib/slaif-capture
sudo chmod 0700 /var/lib/slaif-capture
```

## 3. Enable The Facility And Restart ALL API Workers

```bash
"${DC[@]}" up -d --force-recreate api
```

`REQUEST_CAPTURE_ENABLED`, `REQUEST_CAPTURE_DIR`, and the revision
provenance are **restart-required**: the facility loads them at process
start, and every API worker must be recreated with the overlay. Until this
completes the facility is off and nothing is written. `arm`/`status`/`stop`/
`cleanup`/`inspect` operate on the shared manifest and need **no** restart.

## 4. Safe-Format Or Disable Access Logs For The Window (No Ingress Downtime)

The gateway can capture only bytes that reach it: anything the reverse proxy
rejects upstream (for example Nginx's `client_max_body_size` of 10 m) is not
visible and cannot be captured. Independently, the reverse proxy and any
fronting server write their **own** access logs, which may contain
credential querystrings or `Authorization` values.

Do **not** stop the logging/ingress container while it is serving traffic.
Instead, for the capture window, set the capture vhost to
`access_log off;` (or a safe format without query string/Authorization,
e.g. `log_format safe '$remote_addr $status $request_method $uri';`) and
reload without downtime:

```bash
"${DC_BASE[@]}" exec -T nginx nginx -t
"${DC_BASE[@]}" exec -T nginx nginx -s reload
```

After the window, restore the previous `access_log` configuration and
reload again. The gateway's own logs are tested to be canary-free: capture
artifacts, rejections, and masking failures never print raw request content
or exception detail. The gateway does not control arbitrary external
operator logs on your network; that step is your responsibility for the
window. No client-side proxy is required: you reproduce the request from the
real client as usual.

## 5. Arm A Finite Window For The Exact Verified Key

Identify the gateway key UUID for the reproduction (for example
`slaif-gateway keys list`) and arm exactly one request:

```bash
KEY_UUID="<gateway-key-uuid>"
"${DC[@]}" exec -T --user root api \
  /usr/local/bin/load-production-secrets \
  /usr/local/bin/slaif-gateway request-capture arm \
  --endpoint /v1/responses --key-uuid "$KEY_UUID" --count 1 --ttl-seconds 600
```

- `--count 1` and a finite `--ttl-seconds` are the default operating mode.
- The UUID filter is a **verified-key** filter: the window is claimed only
  for requests whose gateway key verifies to that UUID. Unauthenticated or
  wrong-key requests get their normal 401/400 response and do **not**
  consume the window.
- Do **not** omit `--key-uuid` for production traffic: a window without the
  filter matches **any** request reaching the endpoint, including
  unauthenticated traffic.

## 6. Confirm The Window Is Active

```bash
"${DC[@]}" exec -T --user root api \
  /usr/local/bin/load-production-secrets \
  /usr/local/bin/slaif-gateway request-capture status
```

Expect one `active` session with the expected `remaining` and
`expires_at`.

## 7. Reproduce From The Real Client

Run the real client request you need (an operator action; the facility's
tests use only synthetic data and are not evidence about your traffic).
Record the `X-SLAIF-Diagnostic-ID` header from the response:

```bash
REQUEST_ID="<gw-... from the response headers>"
```

## 8. Inspect The Captured Request

```bash
"${DC[@]}" exec -T --user root api \
  /usr/local/bin/load-production-secrets \
  /usr/local/bin/slaif-gateway request-capture inspect \
  --request-id "$REQUEST_ID" --decode
```

- The **capture** holds the full original request: method, path, query,
  headers, and body bytes (base64; `--decode` renders text, keeps the
  original base64, and labels non-UTF-8 values as a lossy view). Known
  incoming auth values appear only as their masked replacement (a
  recognized gateway key as its public hint).
- The **record** holds the correlation: response status, the verified key
  UUID and how it was verified (normal auth vs the observer's read-only
  probe — malformed-JSON rejections happen before normal auth, so they show
  the probe), the public error code/param/message and the precise local
  rejection facts (structured taxonomy reason with indexes/counts/limits, or
  bounded JSON parser/schema facts with decoder position) for rejected
  requests, the selected client-module id/version/digest for Responses, and
  the deployed revision provenance.
- If the body was not fully captured (limit, disconnect, unconsumed, or
  buffer failure) the record says so with `body_complete=false`, the precise
  `incomplete_reason`, and observed/buffered/stored byte counts, and the
  stored body is empty by design.

Access boundary: the files are readable by their owning OS user (and root)
directly under the `0700`/`0600` modes; the CLI `inspect` command is the
bounded, size-capped convenience path.

## 9. Confirm Automatic Exhaustion / Expiry, Then Clean Up Exactly

- `request-capture status` shows the window flip to `exhausted` (count
  reached) or `expired` (TTL elapsed) automatically. That ends **collection
  only**; captured artifacts persist until explicit cleanup, and neither
  state re-arms even after worker restarts. Storage-full conditions refuse
  further claims the same way.
- Stop and delete exactly the session you used:

  ```bash
  SESSION_ID="<cap-... from the status output>"
  "${DC[@]}" exec -T --user root api \
    /usr/local/bin/load-production-secrets \
    /usr/local/bin/slaif-gateway request-capture stop --session-id "$SESSION_ID"
  "${DC[@]}" exec -T --user root api \
    /usr/local/bin/load-production-secrets \
    /usr/local/bin/slaif-gateway request-capture cleanup --session-id "$SESSION_ID"
  ```

  `cleanup` removes only the session's recognized capture/record artifacts
  and releases its reserved quota; it preserves anything else in the
  directory.
- When capture is no longer needed at all, remove the overlay and recreate
  the API workers without it (facility off):

  ```bash
  docker compose -f docker-compose.production.yml up -d --force-recreate api
  ```

  This is a binary-only feature: there is no database migration to roll
  forward or back, and normal accounting is unchanged throughout (accepted
  requests produce their usage-ledger rows exactly as usual; rejected
  requests create no reservation or ledger rows). Before downgrading to a binary without the
  facility, `stop`/`cleanup` the window; armed windows live in the shared
  manifest, so an unexpired/unexhausted one could resume when a build with
  the facility is enabled again.

## Verification Evidence

Synthetic-versus-real distinction: the repository's tests (and the strategic
review probes) prove the facility with **synthetic** requests against owned
loopback databases and mock backends; they are not qualification of any real
client, model, or provider, and they do not claim your traffic was captured
or inspected. See
[verification/incoming-request-capture.md](../verification/incoming-request-capture.md).
