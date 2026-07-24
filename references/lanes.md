# Candidate lanes

## Contents

- Routing order
- Public Header Lane
- Signed Cookie Lane
- Sticky routing
- Verification and revocation

## Routing order

Access Gateway is the only product-level Revision selector. APIG keeps one shared Site URL and does not receive per-release routes. Selection order is:

1. Valid signed lane cookie.
2. Exact allowed public header matcher.
3. Existing routing cookie bucket.
4. New stable random bucket for percentage Canary.
5. Stable fallback.

The Gateway strips lane headers and platform cookies before proxying the user application. A WebSocket is fixed to the selected Revision at handshake.

## Public Header Lane

```bash
python3 scripts/al_mcp.py release VERSION --canary 5,25,100 \
  --lane-header X-AL-Site-Lane=beta --wait-candidate
```

The platform allowlists the Header Key, such as `X-AL-Site-Lane`. Each release selects its own exact value, such as `beta`, `qa`, or `release-20260724`. Only exact matching is supported.

This does not mean only platform services may set the header. Any HTTP caller may set a public header, so it is a routing selector rather than an authorization boundary. Never use Authorization, Cookie, Host, Forwarded, identity, org, or user headers as a matcher.

## Signed Cookie Lane

```bash
python3 scripts/al_mcp.py release VERSION --blue-green --signed-lane beta --wait-candidate
python3 scripts/al_mcp.py open-lane DEPLOYMENT beta --open-browser
```

The Manager authorizes the caller and returns a short-lived activation URL whose grant is in the fragment. The browser POSTs it to the same-origin Gateway, which consumes the grant once, removes it from the visible URL, and sets an HttpOnly, Secure, SameSite=Lax, path-scoped cookie. Do not paste the activation URL into logs or state files.

Blue-Green `--wait-candidate` automatically adds a signed `preview` lane if no lane was supplied.

## Sticky routing

Sticky Canary is on by default. The signed routing cookie binds Site UID, stable/candidate Deployment UIDs, routing epoch, bucket, and expiry. Anonymous callers receive a random stable bucket. Promotion, cancel, rollback, new Deployment, or lane revocation advances identity/epoch so old cookies are rejected and replaced.

Use `--no-sticky` only when per-request random distribution is explicitly desired. This can make one user alternate versions and is unsuitable for stateful browser validation.

## Verification and revocation

`--wait-candidate` makes a real public request and requires response header `X-AL-Site-Target: candidate`; platform-private smoke alone is not reported as user acceptance.

```bash
python3 scripts/al_mcp.py revoke-lane DEPLOYMENT beta --confirm
```

Revocation advances the routing epoch and invalidates existing sessions for that Deployment. It does not maintain a token denylist. Existing WebSocket connections continue until closed; new connections use the new epoch.

