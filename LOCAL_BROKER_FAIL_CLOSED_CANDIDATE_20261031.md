# Local broker fail-closed candidate evidence — 2026-10-31

## Scope and base

- Isolated worktree: `cq-disaster-stop-hotfix-20261027`.
- Base commit: `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1` (the Render release SHA previously verified read-only).
- The worktree is detached and intentionally uncommitted. Existing modifications and untracked files were preserved.
- No AWS, Render, production, exchange, or credential access was used for this evidence.

## Local changes under test

- `broker.py`: `BROKER_DRY_RUN` now defaults to true; malformed values also fail closed. Only an explicit false-like value can disable dry-run.
- `broker.py`: the single raw `create_order()` boundary independently checks the factual-write mode before consuming the persistent one-shot send authorization.
- `bots/falcon.py`: absent `FALCON_MODE` now defaults to `PAPER`, rather than inheriting `EXECUTION_MODE`.
- `execution_engine.py`: the generic Execution Engine health response now removes `api_key_masked` from the broker status before returning it. This prevents a partially masked key from being included in the public health JSON; it preserves safe mode/configuration booleans.
- Tests extract/execute the relevant AST and do not import the live broker module or read credentials.

## Verification

From this worktree, with pytest plugin autoload disabled and the current directory in `PYTHONPATH`, ran:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONPATH = (Get-Location).Path
& 'C:\Users\giuli\AppData\Local\Python\bin\pytest.exe' -q tests/test_disaster_stop_fallback_route_auth_v1.py tests/test_trading_mode_defaults_fail_closed_v1.py
```

Result: **18 passed in 152.13s**. The route suite blocks socket connection and DNS APIs. The new broker-mode tests use AST-extracted source and a fake exchange; they make no network calls. `git diff --check` passed.

A separate source-only pass ran:

```powershell
& 'C:\Users\giuli\AppData\Local\Python\bin\pytest.exe' -q tests/test_broker_order_constraints_fail_closed_v1.py tests/test_trading_mode_defaults_fail_closed_v1.py
```

Result: **15 passed in 2.25s**. The order-constraint tests interpret extracted functions with synthetic exchange metadata; no broker module import, credentials, network, or exchange call was used.

The isolated Falcon initial-stop failure-containment suite then passed **66 tests in 37.47s**. It exercised AST-extracted Falcon functions with fake broker state while socket connections, DNS, subprocess creation, and `os.system` were blocked. This is still simulated failure/restart policy evidence, not actual exchange or Render persistence proof.

The temporary-directory startup-disk-forensics suite passed **54 tests, 1 skipped, in 114.80s** with socket/DNS connections, subprocess creation, and `os.system` blocked. It uses pytest temporary paths; it does not inspect the Render `/data` disk or prove physical-disk durability.

The terminal disaster-stop emergency-recovery suite passed **91 tests in 60.84s** with socket/DNS, subprocess creation, and `os.system` blocked. It used synthetic broker/registry state; it does not establish BingX order/cancel/readback semantics.

The personal-account position-ownership policy suite passed **17 tests in 75.71s** with socket/DNS, subprocess creation, and `os.system` blocked. It evaluated AST-extracted policy functions with synthetic broker/Registry positions and confirmed manual-position ambiguity is not treated as Falcon ownership. It does not reconcile actual exchange fills or live account positions.

The partial-capability preflight and Falcon central-only reconciliation suites passed **49 tests in 20.66s** with socket/DNS, subprocess creation, and `os.system` blocked. They use extracted functions and synthetic position/Registry evidence; they do not prove production data freshness or real account-side reconciliation.

The Falcon manual-close outcome reconciliation suite passed **40 tests in 38.31s** under the same network/process boundary. Its temporary Registry writer tests use `tmp_path`; this validates local idempotency/ambiguity handling only, not live fill or exchange history reconciliation.

The Falcon real-pilot preflight fail-closed suite passed **54 tests in 19.29s** under the same offline boundary. It uses extracted `main.py` functions and synthetic collectors; it does not read or establish the current production preflight state.

Six focused disaster-stop identity tests passed **6 tests in 17.38s** with network, DNS, subprocess creation, and `os.system` blocked. They cover reservation proof, exact reserved stop-ID submission/audit, mismatched returned IDs, the all-fields-necessary arming gate, fallback denial without persistent reservation, and containment when a stop response has no order ID. This is local fake-exchange evidence only; it does not resolve the official API-documentation ambiguity below.

On 2026-11-01, the fail-closed mode suite passed **5 tests in 21.86s** with socket/DNS, subprocess creation, and `os.system` blocked. It now also parses application Python sources and asserts that the sole raw `create_order()`/`createOrder()` call remains inside `_create_order_with_reserved_attempt`, whose first executable statement denies when `_broker_factual_writes_enabled()` is false. No broker module was imported and no credentials were read.

The execution-health redaction suite passed **3 tests in 0.40s** with socket/DNS blocked. It uses a synthetic masked-key marker, confirms both the redactor and full `execution_engine_health()` response remove it without mutating the source mapping, and does not import broker code.

After adding the health-redaction change, a consolidated regression run passed **123 tests in 219.58s** across execution-health redaction, trading-mode fail-closed, disaster-stop route authorization, broker order constraints, Registry storage readiness/bootstrap guards, and Falcon real-pilot preflight. A temporary pytest plugin made DNS lookups and socket connections fail immediately; plugin autoload was disabled. The temporary plugin was removed after the run. No external service, exchange, or credential was accessed.

The public health audit then found the same masked API-key field nested in `broker_status_payload()` and `bingx_ready_payload()`, which feed public `/execution` and `/execucao` responses. Both payload builders now recursively omit masked keys, masked secrets/signatures, authorization values, and exchange API-key header fields. New AST-isolated tests cover nested status and readiness payloads without importing the broker. The expanded consolidated regression passed **124 tests in 253.39s** with DNS/socket connections blocked and pytest plugin autoload disabled; the temporary blocker plugin was removed afterward.

The first broader entry/fill/position/stop/close/reconciliation/startup run exposed nine failures in `test_broker_managed_close_timeout_semantics_v1.py`: its AST fixtures did not provide the newly added `_broker_factual_writes_enabled` dependency. I updated only those synthetic fixture namespaces to reflect their simulated `live` mode; the dedicated suite then passed **38 tests in 6.42s**. The full selected local regression, rerun with DNS/socket blocked, passed **348 tests, 1 skipped in 422.98s**, including entry/fill gates, managed close and stop replacement, position ownership, disaster-stop containment, close reconciliation (central-only), preflight, Registry guards, health redaction and temporary-disk startup forensics. The direct `test_real_close_reconciliation_v11.py` then passed **76 tests in 18.20s** with DNS/socket blocked and a temporary `ccxt` stub whose exchange-client factory raises if called. This validates offline reconciliation logic only; the actual CCXT adapter was not tested because neither Python installation has `ccxt` and the local pip cache contains no wheel. No network install was attempted. The temporary blocker/stub plugin was removed after testing.

## Additional personal-account privacy gate — 2026-10-31

- Read-only Render metadata query (confirmed `My Workspace`, service `central-robos-bingx`) shows the current service is `standard`, public subdomain enabled, and inbound `ipAllowList` is `0.0.0.0/0`. Latest deploy remains `live` at commit `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1` (2026-10-19). No environment values or HTTP application endpoints were read.
- Static route/source inspection finds no `before_request` authentication hook. Public GET routes include `/execution` and `/execucao` (return broker readiness including balance), `/brokerhealth` (its report prints balance), `/capital` (capital report uses live balance), `/live` (live report includes balance and position details), and `/livepositions` (position report). `/positions/central` returns strategy/position aggregates. These are source-derived exposure risks; no endpoint was called, so no dynamic response was inspected.
- Render's current official inbound-IP rules documentation says IP restrictions for web services/static sites require Scale or Enterprise. Do not recommend or perform a plan upgrade as a “free” fix. No allowlist, authentication environment variable, or production change has been made.
- A local-only HTTP Basic gate is now implemented for direct personal-account reports: `execution_route`, `brokerhealth_route`, `capital_route`, `live_route`, `live_status_v12_route`, `livepositions_route`, `central_positions_route`, `post_execution_safety_check_v1_route`, and the two manual-position report routes. The gate denies absent configuration with HTTP 503, requires Basic credentials, compares UTF-8 bytes in constant time, and blocks cross-site Fetch Metadata/Origin/Referer. It intentionally does not wrap internal bot API endpoints such as `can_open_trade_route`, because local source inspection found bots call those endpoints without HTTP Basic credentials. Broader route privacy still needs review before release.
- Configure only `CENTRAL_PERSONAL_HTTP_USER` and `CENTRAL_PERSONAL_HTTP_PASSWORD` in the service environment before any later deploy; use a unique, strong value and do not send it here. With either missing, the protected report endpoints remain unavailable (503). No credentials were read or created, and this local candidate is not deployed.

## Limits / remaining gates

- These are local synthetic checks, not proof of production configuration, exchange behavior, or trading readiness.
- The current Render values of `ENABLE_REAL_TRADING`, `BROKER_DRY_RUN`, `EXECUTION_MODE`, and `FALCON_MODE` remain unverified. Do not infer them from source defaults.
- A fresh read-only Render service/deploy metadata query does not provide environment-variable values. I did not call the generic `/executionenginehealth` endpoint because the current source's `execution_engine_health()` includes `broker.status_payload(check_ready=False)`, which contains `api_key_masked`. To confirm effective modes without retrieving credentials, a human must inspect only `ENABLE_REAL_TRADING`, `BROKER_DRY_RUN`, and `FALCON_MODE` in the Render Dashboard and report those three values; do not share screenshots or values for other variables. `EXECUTION_MODE` is useful context but does not override the required three safe controls.
- Rechecked the official BingX API reference on 2026-11-01. The real `POST /openApi/swap/v2/trade/order` table explicitly limits `clientOrderId` support to `MARKET` and `LIMIT` (lines 185–210), even though the separate `/order/test` table lists generic client IDs and stop types (lines 249–289). BingX warns that the test endpoint does not enforce every real-order validation (lines 251–256); order-query endpoints support lookup by `clientOrderId` (lines 423–438), but that does not override the real placement restriction. Therefore the current exact stop-client-ID reservation/readback proof is **not established** for `STOP_MARKET`. Keep the stop identity/readback gate fail-closed; do not treat a successful test-order response as proof. No VST/live order was used. Reference: https://github.com/BingX-API/api-ai-skills/blob/main/skills/swap-trade/api-reference.md
- Attempted an offline run of `test_broker_account_client_order_boundary_v1.py` together with three stop-identity suites. Result: 121 passed, 17 failed. Sixteen boundary cases returned `BROKER_WRITE_MODE_DISABLED` because the enforced local PAPER/DRY_RUN defaults correctly deny factual writers; the tests expect the enabled writer path. One adapter-shape test could not construct `ccxt.bingx` because the offline plugin deliberately makes client construction fail. I did not enable LIVE flags or remove the network guard to turn these green. This does not mean the checks above authorize a real order; it identifies that the enabled-writer unit cases need a safer injected fake-mode seam or remain unverified.
- No commit, push, merge, deploy, resource change, or real order was performed.

## Local personal HTTP authentication candidate — 2026-10-31/2026-11-01

- The earlier per-report-endpoint gate described above was superseded after static route/call inspection found legacy report aliases and internal callers. The current local candidate registers one Flask `before_request` gate before every application route and has no endpoint/path exemptions. With either `CENTRAL_PERSONAL_HTTP_USER` or `CENTRAL_PERSONAL_HTTP_PASSWORD` absent/empty, every HTTP request fails closed with 503; otherwise requests require HTTP Basic and receive 401 on missing/incorrect credentials. Cross-site Fetch Metadata and malformed/mismatched Origin/Referer are rejected with 403.
- The internal risk-check POSTs from Cobra, Donkey, Falcon, Meme, Predator, TrendPro, and Turtle now use the same credentials only when the destination is the exact HTTPS origin in `RENDER_EXTERNAL_URL` or the configured local loopback/`PORT`. Untrusted hosts, cleartext non-loopback URLs, userinfo URLs, and invalid `PORT` fail closed without attaching credentials. This prevents bot credentials from being sent to an arbitrary configured risk URL.
- New tests in `tests/test_personal_http_auth_gate_v1.py` exercise the global gate, absence of path exemptions, credential failures, same-origin requests, bot-call credential scope, and invalid-port failure. See the current test run in the handoff/update below; older counts above apply to the superseded implementation only.
- Current focused offline run: **54 passed in 25.39s** across `tests/test_personal_http_auth_gate_v1.py`, `tests/test_history_eventbus_smoke.py`, and `tests/test_trade_lifecycle_shadow_observability_http.py`, with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. The auth suite blocks socket connections and DNS. The two HTTP suites use test clients with synthetic credentials; their module fixtures block network access. `git diff --check` passed after this run.
- Expanded offline regression run: **175 passed in 259.96s** across close-timeout semantics, real-pilot preflight, disaster-stop route authorization, public health redaction, PAPER/DRY_RUN defaults, Registry storage readiness, history/event-bus, lifecycle observability, and the global auth gate. A temporary pytest plugin disabled socket `connect`/`connect_ex`, `create_connection`, and DNS resolution for the entire run; plugin autoload was disabled. This is still local policy/logic evidence and does not exercise live exchange or deployed Render behavior.
- Offline recovery/close run: **196 passed, 1 skipped in 170.84s** across temporary startup-disk forensics, Falcon initial-stop failure containment, and close reconciliation. The same network-blocking plugin was used, and its synthetic `ccxt` module makes BingX client construction fail immediately if attempted. Temporary files use pytest temp directories; this is not proof of Render disk durability or actual exchange readback.
- Entry identity/ownership run: after a first run exposed the writer-contract scanner traversing `.pytest-temp-*` artifacts already inside this worktree, the scanner's directory exclusion was broadened to `.pytest*`. The combined offline/network-blocked rerun passed **169 tests in 160.79s** across broker order constraints, account client-order IDs, writer-contract inventory, position ownership, and manual-close reconciliation. This is a test-harness robustness fix; it does not change the order authorization boundary. The initial run had **3 scanner failures** caused by synthetic pytest files (`main.py` containing `0123456789`), and these were not hidden: the corrected full selection passed.
- To configure the gate later, a human would enter two new, unique values directly in the Render Dashboard for `central-robos-bingx` → **Environment**: `CENTRAL_PERSONAL_HTTP_USER` and `CENTRAL_PERSONAL_HTTP_PASSWORD`. Generate/store them in a password manager and never paste or screenshot them into chat. Add both before any later release: the new code intentionally returns 503 for all routes until both exist. Saving environment changes may restart/redeploy the service; do not do it unless the cost is confirmed as zero and an explicit external-change authorization applies. No credentials were created, inspected, or configured here.
- This remains local, uncommitted code. It is not deployed; production still has its prior behavior. The proposed global gate may affect platform health checks and all web-facing routes, so verify the configured Render health-check path and perform a controlled authenticated smoke test before any future deployment. No AWS, Render, production, exchange, credential, or real-order action occurred.

Reference: BingX-API's [Swap Trade API Reference](https://github.com/BingX-API/api-ai-skills/blob/main/skills/swap-trade/api-reference.md), place-order parameter/response sections and test-order section.

## STOP_MARKET server-order-ID readback candidate — 2026-10-31

- Rechecked the BingX-API primary reference on 2026-10-31. Its real swap `POST /openApi/swap/v2/trade/order` parameter table says `clientOrderId` is supported for `MARKET` and `LIMIT` only; the same reference documents query-by-system-`orderId`. Source: [BingX Swap Trade API Reference](https://github.com/BingX-API/api-ai-skills/blob/main/skills/swap-trade/api-reference.md). This is API-documentation evidence, not a live/testnet request.
- Local-only candidate changes in `broker.py`: retain the durable, unique, one-shot internal reservation and outcome receipt, but omit the reserved ID from the actual `STOP_MARKET` request. Do not consider the stop armed unless the exchange response supplies an order ID and a read-only `fetch_order(order_id, symbol)` returns that exact ID with active status and matching symbol, close side, position side, type, quantity and trigger price. Conflicting ID fields, missing readback, lookup errors or mismatched semantics remain unarmed/reconciliation-required.
- Local-only Falcon changes allow a missing broker-echoed stop client ID only when the creation-time exact-ID readback attestation, internal unique reservation, lifecycle, and later exact order-ID/semantic checks all agree. A nonempty mismatched client ID is not accepted. The readback attestation is carried in position state and Registry metadata for continuity.
- Network-blocked regression: **83 passed** across `tests/test_falcon_client_order_id_collision_guard_v1.py`, `tests/test_falcon_management_safety_v1.py`, and `tests/test_account_client_order_writer_contract_v1.py`; pytest's temporary guard blocked DNS and socket connections and failed if the `ccxt` factory was used. Coverage includes omitted external client ID, exact readback, conflicting ID sources, missing/mismatched ID, inactive order, wrong quantity, Falcon fail-closed continuity, and persistence of the creation-readback attestation into Registry metadata. `py_compile` passed for `broker.py` and `bots/falcon.py`; `git diff --check` passed.
- Adapter-source check (read-only, 2026-10-31): Render's latest deployment query still reports live commit `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`, created 2026-10-19 at 03:17 UTC. A log query restricted to that service, the 2026-10-19 deploy window, and text `ccxt` showed `Successfully installed ... ccxt-4.5.88`; no environment-variable values were queried. The matching upstream tag `v4.5.88` implements linear-swap `fetch_order(id, symbol)` using `swapV2PrivateGetTradeOrder` with the supplied `orderId`, unwraps `data.order`, parses it, and retains the original payload in `info`. Its parser preserves `stopPrice`, `origQty`, `positionSide`, and raw status; it maps `NEW` to unified `open`. This matches the candidate readback gate's adapter shape by source inspection. Primary source: [CCXT 4.5.88 BingX adapter](https://raw.githubusercontent.com/ccxt/ccxt/v4.5.88/python/ccxt/bingx.py) (fetch_order, parse_order, parse_order_status).
- Adapter-source limit (historical note; superseded by the 2026-11-01 worktree state below): this earlier check observed unpinned `ccxt` and no package in the default interpreter. The current worktree now specifies `ccxt==4.5.88`, and the isolated offline environment has that exact package. This makes the local adapter contract reproducible, but does not prove that BingX returns the trigger price for a live untriggered `STOP_MARKET`; only a safe factual exchange readback can establish that. Fake-exchange tests do not prove exchange responses, durable Render persistence, or production behavior. No exchange request, credentials, external write, order, commit, or deploy was used.

## Current official API-schema cross-check — 2026-11-01

- Rechecked BingX-API's maintained swap-trade reference. The real order-placement
  schema documents `clientOrderId` only for `MARKET` and `LIMIT`, while the
  response includes a system `orderId`/`orderID`, order type, quantity, and
  `stopPrice`. The query-order endpoint accepts the system `orderId` and says
  it can retrieve any order status, so querying by exchange-generated ID is a
  documented path that avoids relying on a client ID for `STOP_MARKET`.
- However, the published response schema for query-by-ID refers to the
  `openOrder` response schema, whose listed fields do not explicitly include
  `stopPrice`. The pinned CCXT parser preserves `stopPrice` in `info` if the
  exchange actually returns it; this source/parser contract does not prove the
  live query endpoint returns the trigger field for an untriggered stop.
- Therefore the implementation's requirement to confirm the exact trigger from
  factual readback remains fail-closed and **not externally verified**. Do not
  weaken this check or infer a confirmed stop from only order ID, type, or
  status. A real readback is still required before claiming exchange-level
  validation; this documentation review did not call BingX or create an order.
- Primary reference, reviewed 2026-11-01: [BingX Perpetual Swap Trade API
  Reference](https://github.com/BingX-API/api-ai-skills/blob/main/skills/swap-trade/api-reference.md),
  sections Place Order and Query Order Details / Query Single Open Order
  Status. No credentials, exchange call, or external state change occurred.
- Re-ran `test_disaster_stop_order_id_readback_is_exact_and_fail_closed` with
  the pinned offline Python environment and pytest plugin autoload disabled:
  **1 passed, 11 deselected**. This synthetic case confirms a fabricated
  readback missing the trigger price is not treated as a confirmed stop; it is
  not evidence about the live BingX response schema.

## Pinned CCXT `fetch_order` route contract — 2026-11-01

- Added a second offline adapter contract that invokes the actual pinned
  `ccxt.bingx.fetch_order()` method with the swap market preloaded and replaces
  only the generated HTTP endpoint method with a synthetic response. The test
  confirms the adapter queries `swapV2PrivateGetTradeOrder` using the exact
  exchange `orderId` and BingX symbol, unwraps `data.order`, and preserves the
  raw `STOP_MARKET`, `positionSide`, and `stopPrice` fields in `info`.
- The local CCXT 4.5.88 source includes a swap query-response example with
  `stopPrice` for `TAKE_PROFIT_MARKET`; this is useful adapter/source evidence,
  but does not prove the actual query response for an untriggered `STOP_MARKET`.
  The official BingX response-field table still omits that field, so the exact
  trigger check remains fail-closed pending an authoritative factual response.
- With socket, DNS, `urlopen`, and plugin autoload blocked, both parser and
  query-route tests passed: **2 passed**. No exchange request, credential,
  broker module, order, or external service was used.

## Internal-call compatibility check for the local HTTP gate — 2026-11-01

- A source scan of the seven bot modules found one internal
  `/can_open_trade` POST in each of COBRA, DONKEY, FALCON, MEME, PREDATOR,
  TRENDPRO, and TURTLE. Each request passes `auth=central_personal_http_auth`
  for the exact same target URL; Telegram API requests are outbound to
  `api.telegram.org` and are unrelated to this application's inbound gate.
- Re-ran the AST regression
  `test_internal_bot_risk_requests_use_the_same_environment_auth` with socket
  and DNS connections blocked by the test fixture: **1 passed, 19 deselected**.
  This validates source wiring only; it does not verify deployed environment
  variables or runtime authentication on Render.

## Documented BingX STOP_MARKET acknowledgement/readback contract — 2026-11-01

- The official Swap Trade reference documents `stopPrice` in the successful
  Place Order response, but its Query Single Open Order, Query Order Details,
  Open Orders, and Order History response schemas omit that field. The official
  account WebSocket order-update schema also omits the trigger price. This is a
  documentation-schema constraint, not evidence from a live account response.
- Local broker confirmation now combines two independent facts: the creation
  acknowledgement must contain and validate the exact requested trigger, type,
  symbol, direction, position side, quantity, and active status; a subsequent
  read-only query by the exact exchange-generated order ID must confirm that
  same order remains active and matches symbol, direction, position side, type,
  and quantity. If query readback includes a trigger it must match; a conflicting
  or malformed trigger fails closed. Missing trigger is accepted only when the
  caller passes the creation-ack material-validation result, and the operational
  arming gate independently requires that same creation validation to pass.
- Added synthetic end-to-end regression coverage where the creation response
  includes the documented trigger and the subsequent exact-ID readback omits it,
  plus negative cases for missing creation attestation, conflicting trigger,
  malformed trigger, wrong ID/quantity, and inactive status.
- Network-blocked focused suites passed **100 tests** in **44.14s** across the
  stop identity/confirmation guard, account client-order boundary, Falcon
  management safety, and pinned CCXT BingX readback contract. DNS and socket
  connection entry points and `urllib.request.urlopen` were patched to fail
  before test execution; no exchange request or order was possible.
- Re-ran the complete guarded offline suite after this change:
  `python -I tests/run_falcon_pilot_minimal_offline.py --extra` returned
  **707 passed, 1 skipped, 1 deselected** in **618.31s**, exit code 0. The
  runner's socket/DNS/URL-open/process/`.env` guards were active before
  collection. No network or subprocess access was used by the test run.
- This is a local candidate contract based on published schemas and synthetic
  responses. It does not prove how a real exchange acknowledgement/readback is
  shaped, the persistence behavior of the deployed service, or production
  readiness. No credentials, account data, external service, commit, or deploy
  were used.

## Account client-order boundary rerun — 2026-11-01

- Re-ran `tests/test_broker_account_client_order_boundary_v1.py` using the
  pinned offline Python environment. Before pytest collection, the runner
  replaced socket connect/connect_ex, DNS, `create_connection`, and
  `urllib.request.urlopen` with a hard failure. Its autouse fixture permits
  the factual-send boundary only for this suite's synthetic exchange objects;
  test assertions confirm those fake exchanges receive the expected calls.
- Result: **22 passed in 1.87 s**. This supersedes the earlier recorded 16
  `BROKER_WRITE_MODE_DISABLED` fixture failures for this file; the current
  fixture injects the fake-only authorization explicitly. Production mode
  flags were not changed, no real exchange client request or order was
  possible, and no production, AWS, Render, credentials, or secrets were
  accessed.
- In the same offline environment and with the same pre-collection socket,
  DNS, and URL-open blocks, `tests/test_broker_managed_close_timeout_semantics_v1.py`
  passed **38 tests in 5.35 s**. This exercises synthetic create/cancel/close
  timeout and ambiguous-outcome handling; it does not establish actual
  exchange behavior.

## Stop-order readback contract rerun — 2026-11-01

- `tests/test_bingx_ccxt_stop_readback_contract_v1.py` passed **2 tests in
  1.54 s** in the pinned offline environment. It uses CCXT 4.5.88 with
  synthetic BingX stop-order payloads and replaces network APIs with hard
  failures in the mocked `fetch_order` test.
- Evidence confirms this adapter version preserves raw `STOP_MARKET`,
  `positionSide`, system order ID, amount, status, and stop price through
  parsing. It does not prove that an actual exchange order exists, is
  triggered correctly, or can be canceled/closed in production.

## Exact client-order lookup and retry ambiguity — 2026-11-01

- Corrected `fetch_order_by_id()` to send the documented BingX parameter
  spelling `clientOrderId` (previously `clientOrderID`). Added an offline test
  that captures the exact query parameters and a second test proving an
  exchange `109421` response remains inconclusive: no `query_complete` or
  `NOT_CREATED` attestation is emitted.
- The tests patch socket connect, DNS, and `urllib.request.urlopen` to fail;
  both new cases passed in the pinned offline Python environment. The account
  client-order authority's existing gates also passed **9 tests** rejecting
  missing factual readers and incomplete, ambiguous, or mismatched evidence.
- Re-ran the expanded isolated runner after the change:
  `python -I tests/run_falcon_pilot_minimal_offline.py --extra` returned
  **756 passed, 1 skipped, 1 deselected** in 687.08 s. The symlink-dependent
  test was skipped on Windows; the subprocess-dependent case was intentionally
  deselected because subprocesses are blocked by the runner.
- The current BingX API reference says order-detail lookup accepts
  `clientOrderId` and can retrieve orders in any status, but its error-code
  reference says `109421` can mean an order was filled, canceled, or the ID is
  wrong. Therefore this error cannot establish `NOT_CREATED`; automatic retry
  after a send-claimed/unknown outcome remains fail-closed. These source and
  synthetic tests do not prove live exchange consistency or behavior.
- `py_compile` and `git diff --check` passed. No credential, exchange request,
  order, AWS/Render resource, production data, commit, or deploy was used.

## Replacement STOP_MARKET client-ID boundary — 2026-11-02

- Found an inconsistency in the local candidate: initial disaster-stop creation
  already keeps the account-wide client-order reservation internal and omits
  the unsupported exchange `clientOrderId` field, but replacement-stop creation
  still sent that field and required BingX to echo it before arming.
- Aligned replacement STOP_MARKET creation with the existing initial-stop
  boundary. The durable one-shot reservation remains mandatory internally;
  the exchange payload omits client-order-ID aliases. The returned exchange
  order ID and materially validated active stop acknowledgement remain
  mandatory. If an exchange response includes a client order ID, it must still
  match; an omitted ID is accepted only because this order family is marked as
  not supporting that field.
- Added synthetic regression coverage that removes the echoed client ID,
  verifies the outgoing STOP_MARKET payload omits all client-ID aliases, and
  requires a valid exchange-generated order ID and stop acknowledgement.
- With network APIs blocked before collection, the full related managed-close
  and stop-replacement file passed **39 tests**; the account client-order and
  Falcon management-safety suites passed **86 tests**. No actual exchange
  request, credential, order, production setting, AWS/Render change, commit, or
  deploy was used. This remains local synthetic evidence, not production proof.

## Expanded safety-suite rerun after replacement-stop fix — 2026-11-02

- Re-ran the expanded offline runner from this dirty worktree with the isolated
  `cq-ccxt-4.5.88` environment:
  `python -I tests/run_falcon_pilot_minimal_offline.py --extra` —
  **771 passed, 1 skipped, 1 deselected in 581.28 s**.
- The runner blocks sockets/DNS/HTTP, subprocess/shell execution, and `.env`
  reads before collection; Registry/data paths use temporary storage. The
  focused replacement-stop regression and adjacent broker suites separately
  passed **39** and **86** tests with network access denied.
- This strengthens local regression evidence only. Exchange behavior, live
  account state, Render/Linux disk semantics, production environment values,
  and deployed candidate behavior remain unverified. No credentials, exchange
  request, order, external write, commit, or deploy occurred.
