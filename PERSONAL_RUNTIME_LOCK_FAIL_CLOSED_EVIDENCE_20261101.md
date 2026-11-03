# Personal runtime lock fail-closed evidence — 2026-11-01

## Change

The runtime file-lock helper in `main.py` previously returned success if file
locking failed, and silently proceeded without `flock` when that facility was
unavailable. A second request in the same process could also overwrite the
stored handle. These outcomes could allow duplicate polling/loop ownership.

The helper now denies leadership if `flock` is unavailable, the lock is
already held by this process, another process owns it, or opening, locking,
writing, or flushing the lock record fails. Failed attempts close their file
handle and do not enter `CENTRAL_PROCESS_LOCK_HANDLES`.

Six source-level tests in `tests/test_runtime_file_lock_fail_closed_v1.py`
cover unavailable `flock`, an already-held lock, system/open/write failures,
handle cleanup, and duplicate same-process acquisition. They are included in
`tests/run_falcon_pilot_minimal_offline.py`.

## Verification

- Offline primary runner: **302 passed** in 348.64s. The runner denies sockets,
  DNS, subprocess creation, shell execution, and `.env` reads.
- Offline expanded runner, including Registry atomic-RMW, central-only
  reconciliation, initial-stop failure containment, terminal disaster-stop
  recovery, manual-close and broker-close reconciliation, temporary-disk
  forensics, and synthetic broker-boundary tests: **568 passed, 1 skipped,
  1 deselected** in 327.20s. The skip is a symlink capability check on this
  Windows host; the deselected test requires a cross-process subprocess and is
  outside the offline runner's boundary.
- Focused HTTP, persistence, PAPER/DRY_RUN, disaster-stop authorization, and
  public-health-redaction selection: **107 passed** in 212.31s after using
  pytest's supported plugin configuration.
- `py_compile` for changed runtime and test files passed; `git diff --check`
  passed.

The broker account-order boundary tests now inject the factual-write guard
only inside pytest and use fake exchanges. Their STOP_MARKET fixture omits
`clientOrderId` from the exchange request and validates exact exchange-order-ID
readback. Production trading flags and broker code paths were not enabled.

## Limits

This is local logic evidence only. It does not establish physical cross-process
locking on Render storage, current production environment flags, exchange
STOP_MARKET response semantics, or safe live operation. No AWS/Render resource,
production data, credential, deployment, or trading order was accessed or
changed in this work.

## Revalidation in current workspace — 2026-11-01

- Rechecked the isolated worktree before editing this evidence: detached HEAD
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`; pre-existing modifications and
  untracked files remain preserved.
- Re-ran tests using the existing isolated environment at
  `..\.offline-envs\cq-ccxt-4.5.88\Scripts\python.exe` (Python 3.14.5,
  `ccxt 4.5.88`); no package installation or network access was used.
- Re-ran `tests/run_falcon_pilot_minimal_offline.py`: **302 passed** in
  293.58s. After making the offline socket guard preserve the socket class
  interface required by test fixtures, re-ran `--extra` with the auth and
  public-health suites included: **605 passed, 1 skipped, 1 deselected** in
  471.71s. The skip is the Windows symlink-capability test; the deselected case
  requires subprocess execution, which the runner blocks.
- Re-ran the focused personal HTTP-auth, disaster-stop-route-auth and
  public-health-redaction selection under the same network/secret guards:
  **37 passed** in 163.67s.
- Current `py_compile` for changed runtime and lock/auth/trading tests passed;
  `git diff --check` passed.
- These results do not establish Render process count, cross-process lock
  semantics on its disk, live exchange stop-order readback, production PAPER
  flags, or trading readiness. No AWS/Render writes or deployment occurred.

## Latest offline rerun — 2026-11-01

- Rechecked the same detached `HEAD` and preserved worktree state before this
  rerun. The primary offline runner completed with **302 passed** in 429.96s.
- The expanded offline runner completed with **610 passed, 1 skipped, 1
  deselected** in 662.82s. The Windows symlink-capability case was skipped;
  the cross-process idempotency case was deselected because subprocess
  execution is blocked by the runner.
- `git diff --check` and `py_compile` for `main.py`, `broker.py`,
  `bots/falcon.py`, the offline runner, and the lock/mode test files passed.
- No source code changed during these runs. They validate local candidate
  behavior only; production environment flags, active process count, physical
  Render-disk locking, and LIVE readiness remain unverified.

## Disaster-stop fallback reservation review — 2026-11-01

- Read-only source tracing confirmed that the live Execution Engine carries a factual account-wide entry identity and broker `order_id` into its result, and passes an initial-stop reservation factory to the broker. The broker creates the initial stop with a permanent, pre-send reservation tied to that entry order.
- The legacy post-execution fallback does not currently consume that identity/reservation. Its `_dsf_v1_client_order_id` deliberately returns `None`; `_dsf_v1_attempt_broker_stop_order` refuses to call the broker unless it receives a persistent, unique `RESERVED_PRE_SEND` receipt. The fallback builder does not currently supply one. If the stop remains unconfirmed, it records manual-attention state and activates a lock; it does not send an unreserved stop.
- Automatically reusing the original reservation is unsafe: the account-wide authority is one-shot. A later attempt requires a distinct, persistent attempt authorization with `RECONCILED_NEW_ATTEMPT_AUTHORIZED`, bound to the prior attempt and backed by complete factual lookup showing no order and no fills (unless the authority can prove a pre-send failure with no send claim from its immutable ledger). The authority exposes `authorize_account_client_order_next_attempt`, and Falcon has a separate terminal-stop retry helper, but the reviewed post-execution fallback does not invoke either or establish broker reconciliation evidence. A simple retry counter or a new ID would bypass the safety contract, so no such code change was made.
- Focused offline regression selection across the fallback collision guard, account-wide writer contract, and fallback HTTP route/auth tests: **16 passed, 17 deselected** in 171.14s. Tests ran from the existing isolated Python environment; the route test blocks socket/DNS access. `git diff --check` passed. No source code, AWS, Render, production state, credentials, or orders were changed/accessed.
- Current conclusion: preserve fail-closed behavior. This fallback is not a verified automatic recovery path for an unprotected open position. A safe implementation could reuse the existing authority, but first needs an explicit adapter that distinguishes provable pre-send failures from send-claimed/unknown outcomes and connects the latter to a complete, read-only broker order/fill lookup; then dedicated offline tests must prove ambiguity and unknown outcomes cannot send. Until that exists, an actual stop failure remains a manual incident requiring protection/closure and reconciliation before unlocking execution.

## Reuse/reconciliation and topology recheck — 2026-11-01

- Compared `falcon_handle_terminal_stop_emergency` and `falcon_authorize_position_client_order_retry` with the legacy post-execution fallback. The Falcon path is a distinct, lifecycle-locked emergency close flow. Its retry handling authorizes a contiguous new attempt only for a persisted `NOT_SENT` prior attempt; it does not provide a generic post-entry disaster-stop retry adapter and cannot be called as a drop-in replacement.
- The broker has read-only helpers (`reconcile_order_from_bingx`, `fetch_order_by_id`, and fill readers), but the inspected convenience reconciler reports `ok: true` while carrying fetch errors separately, and its multi-endpoint order listing does not establish a complete negative result when any endpoint failed or is unsupported. It therefore cannot yet serve as the authority's proof that an order and fills were absent. Unknown or partial lookups must remain non-retryable.
- More specifically, `fetch_order_by_id()` returns `ok: false` when it found no matching row, but its result has no `query_complete`/coverage attestation and it combines exact reads with a bounded recent-order fallback. `fetch_order_trades()` filters broad trade-history reads for an exact ID, but its `ok` flag means that some underlying history source succeeded or returned rows; it does not certify complete pagination or complete negative coverage. `reconcile_order_from_bingx()` returns `ok: true` unconditionally and reports source errors in separate fields. None of these result contracts meets `authorize_account_client_order_next_attempt()`'s stricter requirement (`read_only`, `query_complete`, exact attempt identity, `order_found: false`, `fills_found: false`, `ambiguous: false`, and `NOT_CREATED`).
- Refreshed Render read-only metadata for `central-robos-bingx` (`srv-d8rtuv9o3t8c73ehav5g`, workspace `tea-d8gnnuojo6nc73ep3lg0`): Python `python main.py`, `numInstances: 1`, auto-deploy disabled, public ingress, and a mounted 2 GB persistent disk. The available instance-count metric returned 1 at each sampled hourly point (`2026-11-01T04:20:26Z`, `05:20:26Z`). Local source starts bot loops as threads and ends with `app.run`; this plus the Render metadata supports a single-instance/single-launch architecture, but does not prove the runtime OS process/PID count or every active writer.
- No Render environment variables, logs, disk contents, credentials, or secrets were queried. No external configuration was changed. The one-instance finding does not justify distributed C3 by itself; it does not remove the need to prove single-process file/persistence locking and startup behavior.

## Registry writer and persistence audit — 2026-11-01

- Rechecked branch/HEAD/worktree before this local audit: detached `HEAD`
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`; existing modifications and
  untracked evidence/candidate files were preserved.
- Source tracing found the main app installs its persistent Registry wrappers
  at import/startup through `trade_registry_persistent_storage_fix_v1_status`
  with `force=False`. The normal path installs patched load/save functions but
  explicitly does not run migration/bootstrap. The bottom-of-module
  `C3_PERSISTENCE_BOOTSTRAP_V1` is a `no_io=True` status object, not a Registry
  bootstrap. This is consistent with keeping C3 dormant, not evidence that a
  distributed C3 authority is required for the one-instance topology.
- The Registry read/modify/write operations use the shared module-level
  `threading.RLock`; the main-app save wrapper also takes that lock, validates
  the payload, writes a temporary file, and atomically replaces the active
  Registry. `trade_registry.py`'s base save path similarly locks and uses
  `os.replace`. Targeted source searches found the application mutation
  call-sites route through `central_trade_registry.save_registry`; this is
  source evidence, not proof of all production runtime behavior.
- Atomic replacement prevents readers from observing a partially serialized
  JSON file. The base `trade_registry.py` save helper still does not explicitly
  `fsync` the file and parent directory. The local main-app wrapper has since
  been hardened to flush and `fsync` the temp file, atomically replace the
  Registry, then `fsync` the parent directory; errors propagate so the caller
  cannot mark the write successful. This improves the intended Linux runtime
  path but is not physical crash/power-loss evidence for Render's mounted disk.
  Render's one-instance configuration lowers the need for distributed
  coordination, but does not establish cross-process exclusion or physical
  disk durability. A Linux/Render persistence test remains necessary before
  making stronger claims.
- The seven bot modules are conditionally started from `ENABLE_*` environment
  flags and create several background threads on import. Exact production
  flags and the set of active writers were not read; actual active bot/writer
  count therefore remains unknown. No env values, logs, disk data, credentials,
  or secrets were queried.
- Targeted offline synthetic tests:
  `test_registry_two_writers_atomic_rmw_v1.py`,
  `test_registry_remaining_writers_atomic_rmw_v1.py`, and
  `test_trade_registry_live_entry_storage_readiness_v1.py`: **82 passed** in
  50.90s using the pre-existing offline Python environment. These tests cover
  local lock/read-modify-write behavior and fail-closed readiness contracts;
  they do not exercise Render's mounted disk or production-active threads.
- A second offline selection of
  `test_trade_registry_storage_bootstrap_guards_v1.py` and
  `test_runtime_file_lock_fail_closed_v1.py` completed with **36 passed** in
  31.04s. These tests support the no-implicit-bootstrap and local lock
  fail-closed contracts; they do not prove a physical cross-process lock on
  Render.
- No AWS, Render, production data, configuration, credentials, deployment, or
  trading order was accessed or changed. Current personal-use assessment
  remains: a single Render instance with
  process-local coordination is the simpler architecture supported by the
  available evidence; distributed C3 remains unproven as a requirement. The
  remaining physical durability and actual-writer inventory gaps are unresolved
  gates, not a reason to expand C3 by assumption.

## Durable Registry writer local fix — 2026-11-01

- Updated only the local main-app `_trpsf_v1_atomic_write_json` path: create the
  temp file with owner-only mode where supported, serialize and flush, `fsync`
  the file, `os.replace` the target, then open and `fsync` the parent directory.
  Any sync error is raised; `_trpsf_v1_patched_save_registry` catches it and
  marks `last_write_ok` false. The underlying `trade_registry.py` save helper
  remains unchanged and unsynced; the main app installs its wrapper at startup.
- Added `tests/test_trade_registry_atomic_durable_write_v1.py`. With socket
  connect, `connect_ex`, `create_connection`, and DNS resolution blocked, the
  new tests passed **4/4** in 76.40s: file-sync/replace/directory-sync ordering,
  directory descriptor lifecycle, old-target preservation on pre-replace file
  sync failure, and not reporting success when post-replace directory sync
  fails. In the failure case, replacement has already occurred, but caller
  state must remain failed because crash durability is unconfirmed.
- Re-ran the existing live-entry storage-readiness and no-bootstrap guard
  suites with the same network blocks: **34 passed** in 40.17s. `git diff
  --check` passed. Tests used temporary files only. These tests validate the
  logical contract on Windows; they do not prove real POSIX directory `fsync`
  or persistence behavior on Render's disk. No Registry data was modified.
- A fresh read-only attempt to query WSL (`wsl.exe --status` and
  `wsl.exe --list --quiet`) returned `Wsl/E_ACCESSDENIED`; `docker` is not
  available in the current shell. Therefore no real Linux filesystem runtime
  was available for the physical directory-`fsync` test. This is an unresolved
  verification gate, not a reason to weaken the fail-closed write behavior.

## Post-execution disaster-stop fallback integration review — 2026-11-01

- Re-read the current local candidate path. `_dsf_v1_client_order_id()` returns
  `None` until a lifecycle owner supplies a factual canonical identity;
  `_dsf_v1_attempt_broker_stop_order()` refuses any call without a matching
  persistent `RESERVED_PRE_SEND` receipt; and `build_disaster_stop_fallback_v1`
  currently calls it without a reservation. Therefore the fallback cannot
  submit a replacement stop through this path and reports
  `CLIENT_ORDER_ID_RESERVATION_REQUIRED`; if the position remains open without
  a confirmed stop, it activates the manual-attention lock.
- `disaster_stop_fallback_v1_apply_after_execution()` invokes that fallback
  automatically after a real send, but the available path does not establish a
  reconciled new lifetime attempt. Reusing the prior receipt would risk a
  duplicate order; generating a fresh ID without broker reconciliation would
  bypass the account-wide reservation contract. Do not relax either guard.
- This is a confirmed gap in automatic recovery, not evidence of a sent order.
  Before any future LIVE consideration, this path needs an owner-bound, factual
  lifecycle identity, complete read-only broker order/fill reconciliation,
  authorization of a distinct next attempt, and readback proving the new stop
  protects the still-open position. No such fix or live test was attempted.
- Socket/DNS-blocked, offline contract tests passed: **13** selected tests from
  `test_account_client_order_id_v1.py` covering factual NOT_CREATED evidence,
  incomplete/ambiguous/mismatched reconciliation rejection, contiguous retry
  sequence, authoritative sequence-slot readback, and duplicate authorization
  rejection; plus **3** selected broker/Falcon tests proving the fallback
  cannot reach the broker without a matching persistent reservation and that
  exact reservation/readback checks remain fail-closed. This verifies the
  authority boundary, not a complete automatic recovery implementation.

### Primary initial-stop path distinction — 2026-11-01

- A further source trace of `execution_engine.py`, `broker.py`, and Falcon's
  initial-stop containment shows the primary flow already differs from the
  legacy post-execution fallback: the engine persists the entry identity,
  passes a factory for a separate stop reservation into `place_market_order`,
  and propagates the broker result. The broker uses that reservation before
  `create_disaster_stop_order`; when `DISASTER_STOP_REQUIRE_FOR_LIVE` is
  enabled, it reports `LIVE_SENT_BUT_DISASTER_STOP_FAILED` if the entry was
  sent but the stop did not become operationally armed.
- Falcon separately invokes `falcon_handle_initial_stop_failure_containment`
  for a sent entry without an operational stop. The handler persists and locks
  the incident, persists the unsafe entry into the Registry, then requires a
  current ownership recheck before its emergency managed close. That close
  uses a distinct account-wide client-order reservation and operation
  authorization; it does not reuse the entry or initial-stop reservation.
  Ambiguous ownership, incomplete reads, persistence failures, or uncertain
  send outcomes retain the entry lock and require reconciliation.
- Fresh isolated run of `tests/test_falcon_initial_stop_failure_containment_v1.py`
  passed **66 tests** in 33.48s with socket/DNS, subprocess, and URL-opening
  calls blocked. It covers the synthetic confirmed emergency-close path and
  failure/ambiguity containment. This is local logic evidence only; it does
  not verify exchange behavior or production readiness.
- The legacy `/disasterstopfallback` remains a separate manual/legacy route.
  Its broker stop writer still refuses to call the broker without a matching
  persistent reservation. Do not reuse a prior identity or mint a replacement
  without complete, authoritative reconciliation.

## Personal HTTP authentication surface audit — 2026-11-01

- Static inspection found one app-wide `@app.before_request` authentication
  hook, registered before all Flask route handlers in `main.py`. It does not
  exempt endpoints by path or endpoint name; missing auth configuration fails
  with 503, missing/invalid Basic credentials with 401, and cross-site request
  metadata/origin mismatches with 403. The existing offline selection recorded
  above passed 54 tests across the auth gate and HTTP observability/history
  suites; it uses synthetic credentials and blocks sockets/DNS.
- The internal bot helper only returns credentials when the target is the
  exact configured HTTPS `RENDER_EXTERNAL_URL` origin, or the configured
  localhost loopback port. The source-level test checks all seven bot modules
  use this helper for their HTTP risk calls. The current Render environment
  values have not been inspected, so this candidate will return no credentials
  unless its two personal-auth variables are configured.
- Render's official web-service and TLS documentation says inbound HTTP is
  redirected to HTTPS at Render's edge and TLS is terminated there. Clients
  should still use the HTTPS URL directly: an HTTP request reaches the edge
  before that redirect, and this local app hook is not the edge redirect.
- This candidate is not in the currently deployed base release; public ingress
  remains enabled. Therefore the local route gate and redaction tests do not
  establish that the deployed service is authenticated. No service settings,
  environment values, secrets, or production routes were changed or queried.

### Fresh Render read-only confirmation — 2026-11-01

- Re-read the confirmed `My Workspace` Render service metadata and latest deploy.
  `central-robos-bingx` remains on branch
  `codex/c3-final-release-promote-20260910`, one configured instance,
  `python main.py`, persistent `/data` disk (2 GB), `autoDeploy: no`, and an
  empty configured health-check path. Public ingress remains `0.0.0.0/0` with
  the public Render subdomain enabled.
- The latest deployment remains `dep-dbaooagm7kps739mcsqg`, status `live`, at
  base commit `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1` (deployed 2026-10-19).
  It does not include the dirty local authentication/mode/persistence
  candidate. No environment values, logs, disk contents, secrets, or runtime
  process data were requested; no external state was changed.

## Local POSIX test-runtime availability — 2026-11-01

- Rechecked local Linux-runtime options without installing software or using
  network access. `wsl.exe --status` and `wsl.exe --list --quiet` both return
  `Wsl/E_ACCESSDENIED`; neither Docker nor Podman is available on `PATH`.
- Git for Windows Bash is present but does not provide a Linux kernel, so it
  cannot validate Linux `flock`, directory `fsync`, or Render-disk semantics.
  The Windows/mocked durability and lock suites remain useful contract tests,
  but physical POSIX behavior is still unverified. No permission was bypassed
  and no local or production data was changed.

## PAPER defaults and broker-send boundary revalidation — 2026-11-01

- Revalidated the same detached `HEAD` and dirty state before testing; no
  pre-existing files were reset, cleaned, or overwritten.
- Ran the offline Python suite selection
  `test_trading_mode_defaults_fail_closed_v1.py`,
  `test_falcon_real_pilot_preflight_fail_closed_v1.py`,
  `test_main_real_pilot_guard_fail_closed_v1.py`, and
  `test_broker_account_client_order_boundary_v1.py`: **89 passed** in 55.83s.
  Tests use synthetic/monkeypatched mode and fake exchange boundaries; this
  local result is not an environment read or production-mode attestation.
- Candidate defaults fail closed locally when trading-mode values are missing
  or malformed, and the raw broker send boundary independently checks the
  three-condition live-write mode. The reviewed base release has a less-safe
  dry-run default when explicit LIVE plus real-trading flags are configured;
  this describes a possible misconfiguration, not the current Render values.
- Current deployed values of `ENABLE_REAL_TRADING`, `BROKER_DRY_RUN`,
  `EXECUTION_MODE`, and `FALCON_MODE` remain unknown. The available Render MCP
  can inspect service/deploy metadata but has no safe operation to read only
  those selected non-secret values; no generic env listing or endpoint that
  returns broker details was used because it could expose secrets or balances.
- `git diff --check` passed after updating this evidence. No source code,
  environment, AWS, Render, production data, credential, deployment, or order
  was changed or accessed.
- Re-ran the global personal HTTP-auth gate and HTTP observability/history
  selection: **54 passed** in 24.35s across
  `test_personal_http_auth_gate_v1.py`, `test_history_eventbus_smoke.py`, and
  `test_trade_lifecycle_shadow_observability_http.py`. Their fixtures block
  socket/DNS access and use synthetic credentials. This validates the local
  candidate gate only; the deployed service has not received this code and
  production has not been configured with the required personal-auth values.
- Executed the current main-app atomic JSON writer by AST extraction against a
  fresh temporary directory: write/readback passed; a simulated `os.replace`
  failure propagated and preserved the prior target bytes. The probe performed
  no network calls and removed its temporary directory on exit. It reported
  `fsync_performed: false`; this is atomic-replacement evidence only, not crash
  durability or proof about the mounted Render disk.
- Re-ran stop identity, Falcon management-safety, and account-level client
  order writer suites in the offline environment: **83 passed** in 71.83s.
  These use synthetic state/fake exchange fixtures; they do not prove BingX's
  live untriggered STOP_MARKET behavior, a real server-side stop readback, or
  recovery from an actual exchange/network failure.
- Re-ran the personal position-ownership limit, manual-close outcome
  reconciliation, and real-close reconciliation suites: **133 passed** in
  111.53s in the offline Python environment. These validate local synthetic
  ownership/close paths; they do not prove exchange state, live fills, or
  production Registry reconciliation.

## Fresh Render release/topology check — 2026-11-01

- Read-only `get_service` in the confirmed `My Workspace` returned
  `central-robos-bingx` (`srv-d8rtuv9o3t8c73ehav5g`): Python `python main.py`,
  one configured instance, public ingress `0.0.0.0/0`, no health-check path,
  auto-deploy off, Standard plan, and a 2 GB `/data` disk. This is configuration
  metadata; it does not reveal the running PID/thread or active bot flags.
- Read-only `list_deploys(limit=1)` returned live deployment
  `dep-dbaooagm7kps739mcsqg` at commit
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`, created 2026-10-19. This equals
  the local detached base `HEAD`, not the dirty/untracked candidate worktree.
- GitHub's read-only branch search confirms the deployment branch name exists,
  but the attempted branch detail fetch was rejected by the connector; its
  current remote SHA was not established. No remote code was changed.
- No environment-variable names or values, logs, disk data, credential,
  secret, deploy, or production endpoint were accessed. No external state was
  changed. The local HTTP-auth and fail-closed-mode candidate is still not the
  deployed release; public ingress remains enabled, so the service is not
  certified as privately authenticated or safe for LIVE.
- A permitted read-only browser inspection was attempted only after the user
  had authorized using the confirmed Render workspace. Computer Use stopped
  before any navigation or input because it could not confidently determine
  the current browser URL. No page, form, or environment value was opened or
  changed. The safe non-secret mode and bot-enable values remain a manual
  verification item; do not send screenshots or any other environment values.
- Current dependency reproducibility check: `requirements.txt` lists bare
  `ccxt`, the isolated offline environment contains 4.5.88, and no newer CCXT
  wheel appeared in the local pip cache. The latest official upstream release
  page returned v4.5.90 and lists a BingX order-rejection-code mapping change.
  Since 4.5.90 is unavailable in the approved offline environment, its adapter
  behavior has not been tested here; requirements remain unchanged rather than
  treating 4.5.88 test results as proof for an unconstrained future build.
- Read-only source comparison of official tags `v4.5.88` and `v4.5.90`
  (`python/ccxt/bingx.py`) found the common order-status mapping unchanged.
  The newer parser defensively reads fallback fee currency fields and parses
  `fee.cost` to a number; the older parser returns that fee cost as a string.
  A synthetic offline parse with installed CCXT 4.5.88 reproduced the string
  result. The Registry's `_rcr_v1_fee` explicitly passes `fee.cost` through
  `safe_float`, so that observed type difference is normalized at that
  consumer. This is limited source/consumer evidence, not proof of all BingX
  adapter behavior or live exchange compatibility. No dependency pin or code
  change was made because v4.5.90 could not be installed/tested offline.

## Expanded offline runner with durable Registry-write test — 2026-11-01

- Added `test_trade_registry_atomic_durable_write_v1.py` to the existing
  `--extra` case list in `tests/run_falcon_pilot_minimal_offline.py`. This is a
  test-discovery change only; it preserves the runner's network, DNS,
  subprocess, shell, and `.env` guards.
- Executed with the existing isolated environment:
  `..\.offline-envs\cq-ccxt-4.5.88\Scripts\python.exe -I .\tests\run_falcon_pilot_minimal_offline.py --extra`
  Result: **614 passed, 1 skipped, 1 deselected** in 545.25s. The skip is the
  host's symlink-capability case; the deselection is the cross-process test
  excluded by the runner because subprocess creation is intentionally blocked.
- This validates the candidate's synthetic/offline suite on Windows and makes
  the durability tests repeatable through the guarded runner. It does not
  validate POSIX directory `fsync`, physical Render-disk persistence, external
  service behavior, or production readiness.

## Personal trading-mode default regression — 2026-11-01

- Extended `tests/test_trading_mode_defaults_fail_closed_v1.py` to exercise
  the environment-derived mode defaults for Cobra, Donkey, Falcon, Predator,
  and TrendPro; the broker's default flags; and the Execution Engine's default
  mode/enable flags. The cases specifically assert that a global
  `EXECUTION_MODE=LIVE` does not silently promote Falcon or Predator from
  PAPER.
- Ran the focused module using the isolated Python environment:
  `..\.offline-envs\cq-ccxt-4.5.88\Scripts\python.exe -I -m pytest -q -p no:cacheprovider -p no:debugging .\tests\test_trading_mode_defaults_fail_closed_v1.py`
  Result: **7 passed** in 21.47s.
- These are local source-contract and mocked-boundary checks; they do not
  establish current production environment values, exchange behavior, or LIVE
  readiness. No production controls or external services were changed.
- Fresh rerun with socket, DNS, subprocess execution, and URL opening blocked
  passed **7 tests** in 22.54s. The first ad-hoc guard attempt failed during
  `unittest.mock` import because its temporary `Popen` replacement was a
  function; the guard was corrected to preserve the class interface and the
  final offline run passed. No product test or source change was needed for
  this harness issue.
- Re-ran the mode-default module together with the broker account/client-order
  boundary and Falcon real-pilot preflight suites, explicitly adding the local
  project root to Python's import path while retaining isolated mode:
  **85 passed** in 42.26s. An initial invocation without that path adjustment
  stopped during collection (`ModuleNotFoundError: broker`); it was a test
  invocation issue, corrected before this passing run.

## Read-only writer/deployment overlap check — 2026-11-01

- Static source review: `main.py` loads each bot only when its `ENABLE_*`
  setting is truthy; the individual bot modules start scanner and watchdog
  threads (Falcon also starts management/summary threads). Registry writes in
  one process share `trade_registry._lock`. The deployed base `HEAD` contains
  a process file lock for selected background loops; the current dirty
  candidate makes missing `fcntl` fail closed.
- Read-only Render `list_logs` searches for `BOT CARREGADO` on 2026-10-19
  returned the seven bot names at four distinct instance IDs during four
  sequential deployments. New-runtime startup log timestamps were 02:21:19,
  02:50:26, 02:59:58, and 03:20:19 UTC; deploy completion events followed at
  02:21:21, 02:50:28, 03:00:00, and 03:20:23. This is evidence of module load
  at replacement startup, not proof of concurrent Registry writes. Targeted
  searches for `SIGTERM`, `Stopping`, and `Shutdown` returned no matching app
  log lines.
- Current read-only Render service metadata reports `numInstances: 1` and one
  attached persistent disk at `/data`. Official Render disk docs state that a
  disk is accessible to only one service instance, prevents zero-downtime
  deploys, and that redeploy stops the old instance before starting the new
  one: https://render.com/docs/disks. Thus ordinary redeploy overlap is not
  supported for this observed topology; abnormal platform behavior and actual
  runtime environment values remain unverified.
- This evidence does not justify adding or activating distributed C3 for the
  current single-instance, single-disk personal topology. Keep C3 dormant and
  out of the critical path; reassess if instance/service/disk/process topology
  changes. No service state, logs, disk data, environment variables, secrets,
  or production settings were changed.
- Rechecked local Linux-runtime availability: both `wsl --status` and
  `wsl --list --quiet` return `Wsl/E_ACCESSDENIED`; Docker and Podman are
  unavailable. The physical POSIX directory-fsync/lock gates therefore remain
  unrun in this Windows environment. Preserve the existing fail-closed result;
  Windows tests are not a substitute for this Linux evidence.

## Public HTTP exposure and local authentication candidate — 2026-11-01

- Read-only Render metadata reports the service URL enabled and ingress
  allowlist `0.0.0.0/0`. The latest deployed commit is the isolated worktree's
  base `HEAD` (`0ecced0d...`). Static inspection of that exact `HEAD:main.py`
  found the public `/livestatus` route returns `build_live_report()` and no
  application-wide `@app.before_request` authentication hook. The report
  builder reads and formats broker balance, broker positions, and Central live
  positions. This identifies a potentially sensitive publicly reachable
  report path; no HTTP endpoint was called and no user/account data was read.
- The dirty local candidate adds a global fail-closed HTTP Basic gate before
  every application route, blocks cross-site requests, returns 503 if its
  auth environment values are absent, and has a helper that supplies auth only
  to the configured service HTTPS origin or configured loopback. Added a
  source-contract assertion that each of the seven bot clients passes the
  exact same risk-gate URL to both its request and the auth helper. Added a
  real-Flask-dispatch test that registers the exact source hook on Flask and
  exercises a synthetic `/livestatus` route, missing/wrong/valid Basic auth,
  unknown paths, and cross-site rejection. Added an integration regression
  against the actual imported Flask app: unauthenticated `/livestatus` is
  rejected before `build_live_report()` runs, while valid synthetic credentials
  reach a mocked report builder. The focused offline suite for this gate,
  public health redaction, and lifecycle HTTP observability passed **49 tests**
  in 35.95s. Tests use synthetic credentials and blocked network access; they
  do not prove deployed protection.
- Production auth values were not read, and the current release has no source
  hook that would enforce them. Consequently, setting environment values alone
  would not protect the current deployed routes. The candidate is not in the
  deployed release; no commit, push, deploy, environment change, or external
  state change was made. Treat deployment of a reviewed auth fix as a separate
  external step; do not expose any secrets when verifying it.

## LIVE Central Risk bypass regression — 2026-11-01

- Rechecked the exact local worktree before changing code: detached `HEAD`
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`; all prior modifications and
  untracked files were preserved.
- Static review found that COBRA, DONKEY, and TRENDPRO could ALLOW an entry in
  `EXECUTION_MODE=LIVE` when their central risk connector was disabled or when
  an HTTP/network error occurred with the `*_FAIL_CLOSED` override set false.
  PREDATOR could also ALLOW in LIVE when `PREDATOR_REQUIRE_CENTRAL_RISK=false`.
  Production environment values were not read; this was a code-path finding,
  not evidence that production uses any such override.
- Local candidate correction: in LIVE, the three connector functions now
  force fail-closed for missing/failed central decisions and DENY when the
  connector is disabled. PREDATOR now DENYs LIVE if its central risk
  requirement is disabled. Explicit fail-open behavior remains available to
  the three connectors outside LIVE for compatibility with PAPER workflows.
- Added `tests/test_live_central_risk_gate_fail_closed_v1.py` with synthetic
  function harnesses covering disabled LIVE gates, HTTP 503 with fail-open
  overrides, PAPER compatibility, and Predator's disabled requirement. All
  **10 targeted tests passed**. The network/subprocess/`.env`-blocked primary
  offline runner, including this regression, then passed **312 tests** in
  337.12s. `git diff --check` passed.
- This is local code/test evidence only. It does not establish production
  configuration or deployed behavior. The Render release remains at the base
  `HEAD`; no commit, push, deploy, AWS/Render write, secret access, or order
  occurred. This does not certify LIVE readiness.

## Expanded guarded offline suite — 2026-11-01

- Revalidated the isolated worktree before recording this result: detached
  `HEAD` `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`; all modified and
  untracked files were preserved. `git diff --check` passed.
- Command: `..\.offline-envs\cq-ccxt-4.5.88\Scripts\python.exe -I tests/run_falcon_pilot_minimal_offline.py --extra`.
- Result: **627 passed, 1 skipped, 1 deselected** in **615.94s**; exit code 0.
  The repository runner blocks network/DNS and subprocess/shell access for its
  tests. The added LIVE central-risk fail-closed regression was included.
- This remains synthetic/local evidence: it does not prove current AWS,
  Render, or production configuration, deployed behavior, Linux disk
  durability, or LIVE-trading readiness. No commit, push, deploy, external
  mutation, secret access, or real order was performed.

## Pinned CCXT stop-readback parser contract — 2026-11-01

- `requirements.txt` previously declared unpinned `ccxt`; the observed
  deployed build and available offline environment both use `4.5.88`. Pinned
  the dependency to `ccxt==4.5.88` so the stop-readback adapter behavior is not
  silently changed by a later dependency resolution.
- Added `tests/test_bingx_ccxt_stop_readback_contract_v1.py`. With a synthetic
  BingX swap STOP_MARKET response, the exact installed adapter preserves the
  exchange order ID, raw `type`, `positionSide`, and `stopPrice` in `info`,
  parses the amount and active status, and maps the trigger to `stopLossPrice`.
  It normalizes the symbol to `BTC/USDT`; the broker validator compares the
  normalized symbol identity and reads raw stop semantics from `info`.
- Ran the focused test with the pinned offline Python environment and socket,
  DNS, and `urlopen` network access blocked: **1 passed**. No API request,
  credentials, or exchange client connection was made. `git diff --check`
  passed.
- This proves only the local adapter parser shape for the pinned package, not
  BingX's actual STOP_MARKET response/readback, deployed dependency state,
  broker behavior against an exchange, or trading readiness. No external
  change, commit, push, deploy, or order occurred.
- After registering the new contract test in the offline runner's `--extra`
  suite, reran the full guarded suite: **628 passed, 1 skipped, 1 deselected**
  in **621.04s**, exit code 0. The runner blocks network/DNS, subprocess/shell,
  and `.env` access. `pip check` reported no broken requirements and
  `git diff --check` passed.
- The runner's base suite, which additionally exercises account client-order
  identity and real-position ownership/preflight contracts, passed **312
  tests** in **310.48s**, exit code 0, under the same network/process/`.env`
  boundary.

## Linux durability lab availability — 2026-11-01

- Checked for local Linux/container execution without changing the repository:
  `wsl.exe` is present, but `wsl.exe --list --quiet` returns
  `Wsl/E_ACCESSDENIED`; Docker and Podman executables are not installed. The
  available `bash.exe` resolves only to the WindowsApps launcher and does not
  provide a Linux runtime.
- Therefore the current turn could not run Linux `flock`, `/proc`, or physical
  directory-fsync durability gates. The Windows offline test results above are
  not substituted for those Linux guarantees; fail-closed behavior remains
  required until the sealed Linux lab can run.
- No test was run against live Registry data or a mounted production disk. No
  AWS/Render/production change, credential access, commit, push, deploy, or
  trading action occurred.

## PAPER defaults and LIVE central-risk denial recheck — 2026-11-01

- Re-ran `tests/test_trading_mode_defaults_fail_closed_v1.py` and
  `tests/test_live_central_risk_gate_fail_closed_v1.py` with the pinned offline
  Python environment, pytest plugin autoload disabled, and socket/DNS/URL-open
  calls replaced by immediate failures: **17 passed** in **22.39s**.
- These tests cover the local defaults and deny behavior for LIVE entry checks
  when the central gate is missing, disabled, or errors. This is synthetic
  policy evidence only; it does not establish the Render environment values or
  deployed runtime behavior. No exchange, AWS, Render, secret, or order access
  occurred.

## Runtime lock name collision guard — 2026-11-01

- Static inspection found four named shared-loop locks and one generated
  `bot_telegram_<key>` lock family. Added a source-level regression that checks
  fixed lock-name uniqueness, case-normalized `BOT_CONFIGS` key uniqueness,
  and disjointness between bot-specific and shared-loop lock names.
- Ran `tests/test_runtime_file_lock_fail_closed_v1.py` in the pinned offline
  environment with socket, DNS, and URL-open calls blocked: **7 passed** in
  **33.14s**. The new test is static; existing cases exercise fail-closed lock
  behavior using temporary directories and synthetic `flock` outcomes.
- This does not prove Linux `flock`/`/proc`/directory-fsync behavior or current
  production ownership. No data, AWS/Render state, secrets, or orders were
  accessed or changed.

## Integrated guarded offline regression — 2026-11-01

- Re-ran `tests/run_falcon_pilot_minimal_offline.py --extra` with the pinned
  offline Python environment. The runner blocks network/DNS/URL opening,
  subprocess creation, and secret-file access before pytest collection.
- Result: **629 passed, 1 skipped, 1 deselected** in **635.15s** (exit code 0).
  This includes the runtime lock-name collision guard and the CCXT
  `fetch_order()` route contract using a synthetic HTTP method stub.
- This remains local/synthetic evidence; it does not verify live BingX
  STOP_MARKET readback fields, Linux physical durability, production flags,
  deployed code, or production coordination. No AWS/Render/production change,
  credential access, commit, push, deploy, or trading action occurred.

## Public broker health exception redaction — 2026-11-01

- Local review found broker status/readiness helpers returning raw exception
  text and import-error text in diagnostic payloads. Replaced those strings
  with stable error codes and exception class names; added a canary regression
  proving the synthetic secret fragment is absent from both outputs.
- Ran `tests/test_execution_engine_public_health_redaction_v1.py` with socket,
  DNS, and URL opening replaced by immediate failures: **5 passed** in **40.06s**.
- The app-wide local auth gate remains required; this redaction is defense in
  depth and does not make an undeployed candidate production-safe. No real
  secrets were read. No AWS/Render/production changes, deploy, commit, or order
  occurred.

## Malformed trading-mode configuration guard — 2026-11-01

- Added regressions for malformed `BROKER_DRY_RUN`, malformed
  `ENABLE_REAL_TRADING`, an unrecognized `EXECUTION_MODE`, and missing
  `BROKER_DRY_RUN` while other simulated flags request LIVE. Each combination
  keeps the raw broker-write gate false. Also verified an unrecognized Falcon
  mode string is not equal to the exact `LIVE` token.
- Ran `tests/test_trading_mode_defaults_fail_closed_v1.py` with socket, DNS,
  and URL opening blocked: **9 passed** in **27.34s**.
- This validates parser/default behavior locally only. It does not prove the
  actual Render variables or deployed code; those remain unverified. No
  credentials, exchange, AWS, Render, production state, or orders were touched.

## Disaster-stop readback contract recheck — 2026-11-01

- Ran the focused CCXT/BingX adapter and broker exact-order-ID readback tests
  with socket connect, DNS, and URL opening blocked: **3 passed, 11 deselected**
  in **1.18s**. Coverage confirms the adapter queries by system `orderId`,
  preserves raw `STOP_MARKET`/trigger fields, and broker arming rejects an
  identity mismatch, conflicting IDs, wrong quantity, inactive status, or a
  missing requested ID.
- The only initial failures were test-harness setup: `-I` omitted the project
  root from `sys.path`, then an overly broad socket stub conflicted with the
  test's own monkeypatch. The corrected isolated invocation passed; no code
  change was required.
- This is synthetic adapter-contract evidence, not confirmation of BingX's
  real untriggered STOP_MARKET response. No exchange/network calls or orders
  occurred.

## Startup and temporary-persistence regression — 2026-11-01

- Ran `test_trade_registry_atomic_durable_write_v1.py`,
  `test_trade_registry_live_entry_storage_readiness_v1.py`, and
  `test_startup_disk_forensics.py` with socket connect, DNS, and URL opening
  blocked. Result: **62 passed, 1 skipped** in **168.38s**.
- These tests exercise atomic JSON replacement and file/directory sync ordering,
  failure preservation, fail-closed startup readiness, bounded metadata-only
  disk scanning, and temporary-directory persistence. They do not establish
  physical Linux filesystem durability or behavior on Render's mounted disk;
  the Linux/runtime gate remains open.
- No Registry/production data, AWS, Render, credentials, or exchange were
  accessed or modified; no commit, deploy, or order occurred.

## Process-lock contender metadata preservation — 2026-11-01

- Review found that opening a lock file with mode `w` truncated its contents
  before the nonblocking `flock` attempt. A process that lost the lock could
  therefore erase the current holder's metadata even though it never became
  leader. Changed the open mode to `a+`; the file is truncated and rewritten
  only after exclusive lock acquisition succeeds.
- Strengthened the busy-lock test with existing owner metadata and asserted a
  rejected contender preserves it. Also asserted that the winner writes valid
  JSON metadata after acquiring the lock. The full lock module passed with
  network blocked: **7 passed** in **35.01s**.
- This validates the open/truncate sequence with a synthetic contention
  result, not cross-process Linux `flock` behavior. Linux/runtime validation
  and Render deployment remain unverified. No production change occurred.

## Final integrated guarded regression after lock and fail-closed updates — 2026-11-01

- Re-ran `tests/run_falcon_pilot_minimal_offline.py --extra` after the latest
  public-health redaction, malformed-mode regressions, and lock metadata
  preservation fix. The runner blocks network/DNS/URL opening, subprocess
  creation, and secret-file access before pytest collection.
- Result: **632 passed, 1 skipped, 1 deselected** in **577.32s** (exit code 0).
- This integrated result remains Windows/local evidence. It does not verify
  Linux `flock` or physical directory-fsync behavior, production environment
  values, deployed release parity, real BingX STOP_MARKET readback, or Render
  startup/recovery. No external state, credentials, or orders were touched.

## Render deploy parity read-only refresh — 2026-11-01

- Queried the five most recent deploy records for the confirmed Render service
  in the confirmed workspace. The active deploy remains `dep-dbaooagm7kps739mcsqg`,
  status `live`, from commit `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`
  (`fix(registry): prefer canonical closed identity fields`), deployed
  2026-10-19 03:20 UTC. The other four returned records are deactivated.
- This deployed commit equals the isolated worktree base HEAD but not the
  dirty local candidate. The query read deploy metadata only; no env values,
  logs, secrets, or runtime data were requested. No service change or deploy
  occurred.

## Focused personal-safety regressions — 2026-11-01

- Re-ran mode-default fail-closed checks, personal HTTP authentication,
  process-lock behavior, disaster-stop fallback authorization, and public
  broker-health redaction using the installed Python 3.14 interpreter. Result:
  **55 passed** in **251.77s**. These are local tests; route/auth suites block
  socket connection and DNS in their fixtures. No exchange client was called.
- The separate CCXT STOP_MARKET contract module could not be collected in this
  interpreter because `ccxt` is not installed (`ModuleNotFoundError`). No
  package was installed and no network fallback was attempted. This does not
  invalidate the earlier full guarded offline regression result, but this
  interpreter did not re-run that CCXT-specific module.
- No source code changed during this focused rerun; no production flags,
  Registry data, credentials, AWS, Render, or exchange were accessed or
  modified. The Render log query for current bot startup entries returned
  HTTP 503, so active runtime writer/process inventory remains unverified.
- Checked the available Python 3.11 and 3.14 interpreters, their local package
  locations, pip cache locations, and Downloads for an existing `ccxt` install
  or wheel. None was found in those locations; the 3.11 interpreter also
  lacks pytest/Flask. A follow-up search across the broader Codex directory
  found the existing offline environment `feito/.offline-envs/cq-ccxt-4.5.88`
  and wheelhouse `feito/offline-wheelhouse-ccxt-20261023`; no package download
  or installation was attempted.
- Additional static review of the exact deployed base `HEAD:main.py` confirmed
  `/disasterstopfallback` and `/disasterstop` accept `GET`, pass query-string
  `commit` and `ack` through to the broker-stop fallback builder, and contain
  an allowed-ack path that can call the broker stop-order helper. With the
  Render service publicly reachable and no application-wide auth hook in that
  release, this is a potential unauthenticated stop-order creation surface.
  No endpoint was called and no order was sent. The local candidate changes
  GET to preview-only and requires authenticated POST, but is not deployed.
- Ran `tests/test_bingx_ccxt_stop_readback_contract_v1.py` using the existing
  offline environment with CCXT **4.5.88**. Result: **2 passed** in **1.00s**;
  its fixture blocks socket connections, DNS, and URL opening. This verifies
  the client-library contract with synthetic responses only, not the live
  BingX payload or real stop protection.

## Latest full guarded offline regression — 2026-11-01

- Re-ran `tests/run_falcon_pilot_minimal_offline.py --extra` with the existing
  `cq-ccxt-4.5.88` environment. Before pytest collection, the harness blocks
  network/DNS/URL opening, subprocess creation, and `.env` file access.
- Result: **632 passed, 1 skipped, 1 deselected** in **588.25s** (exit code 0).
  This includes the CCXT synthetic STOP_MARKET contract and the local HTTP,
  trading-mode, registry-persistence, startup and lock regressions.
- This remains Windows/local evidence. It does not verify the live exchange
  response, Render's runtime flags/process inventory, real Linux flock or
  physical `/data` durability, or the deployed candidate. No credentials,
  order, AWS or Render mutation was involved.

## Auto-real bridge remains preview-only under current trading policy — 2026-11-01

- Reviewed the isolated candidate route `/autorealbridge` and alias
  `/auto/realbridge`. GET requests carrying any `execute`, `commit`, or `ack`
  field are rejected; POST requests require the execution-auth hook, reject
  query parameters, and validate the complete confirmation tuple.
- Tightened the route to refuse every real-execution request with
  `LIVE_EXECUTION_DISABLED_BY_SAFETY_POLICY`, even when the request is
  authenticated and the confirmation tuple is complete. Only preview requests
  can reach the processor, with `execute=False` and `dry_run=True`. Synthetic
  tests assert no processor call is made for refused live requests.
- Focused HTTP/auth/mode regression: **52 passed**. Full guarded offline suite
  `tests/run_falcon_pilot_minimal_offline.py --extra`: **641 passed, 1 skipped,
  1 deselected** in **628.56s** (exit code 0). The runner blocks networking,
  subprocess creation, and `.env` reads before test collection.
- This is local Windows evidence only. It does not prove production route
  behavior, deployment parity, exchange behavior, or readiness for LIVE. No
  request was made to the service, no order was sent, and there was no AWS,
  Render, production, commit, or deployment change.

## Authenticated GET mutation guard — 2026-11-01

- Static route review found legacy HTTP handlers where GET requests could
  carry mutation intent in query parameters (including history rotation,
  cooldown release, live-audit acknowledgement, Registry repair/sync and
  notification flags). A path/argument guard now rejects those GET requests
  with HTTP 405 before route dispatch; preview GETs with false-like flags
  remain available. The intended state-changing method remains POST behind
  the app-wide authentication hook.
- Focused HTTP/auth, preview-only bridge, disaster-stop and trading-default
  regressions: **54 passed**. Full guarded offline suite
  `tests/run_falcon_pilot_minimal_offline.py --extra`: **643 passed, 1
  skipped, 1 deselected** in **680.39s** (exit code 0). The harness blocks
  networking/DNS/URL opening, subprocess creation and `.env` reads before
  pytest collection.
- `git diff --check` passed before this report update. This is local Windows
  evidence only; no endpoint was invoked, no order was sent, and no AWS,
  Render, production, commit or deployment change was made. Production still
  runs the previously observed base release, so these candidate protections
  are not effective there until a separately validated, zero-cost deploy.

## Expanded GET mutation audit and regression — 2026-11-01

- A broader static scan found legacy GET routes whose handlers write by
  default even when the query omits an action flag: `/realpnlr`,
  `/realpnlr/text`, `/adaptive/build`, and the v1 outcome-evaluator route; it
  also found executive policy routes that commit by default unless
  `check_only=true`, plus explicit policy auto-release/priority/evaluation
  actions. The earlier generic query-field guard did not cover these default
  behaviors, so its 643-test green run was not sufficient for this invariant.
- The local guard now blocks default-writing GET routes unless their handler's
  exact read-only mode is explicitly selected; it blocks policy actions with
  no read-only mode, action/confirmation/ack flags, and registry update/close
  flags. False-like query representations (`0`, `false`, `no`, etc.) are
  accepted only where the underlying handler treats them as non-mutating.
  Preview/status GETs remain allowed; POST remains subject to the global
  authentication gate.
- A first focused run caught 11 test expectation/normalization failures; those
  were fixed by matching each handler's boolean semantics and by asserting
  that explicit read-only requests reach the synthetic handler. The rerun
  passed **78 tests**. The full guarded offline suite then passed **699 passed,
  1 skipped, 1 deselected** in **601.48s**, exit code 0. `py_compile` and
  `git diff --check` also passed. Tests blocked network/DNS/URL access,
  subprocess creation and `.env` reads; they used only synthetic Flask routes
  and temporary local state.
- This remains a local candidate, not a production fix. No app endpoint,
  exchange, AWS, Render or production state was called or changed; no order,
  commit or deployment occurred. Production still runs base commit
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`, so its public-route behavior is
  unchanged.

## GET action-route closure and read-only risk checks — 2026-11-01

- The broader AST review found additional state-changing handlers reachable
  through GET: PAPER lifecycle update/test-close/test-TP50, execution-engine
  run/verify (dry-run routes), and risk-registry GET checks that invoked
  `autosync_trade_registry`. These semantics were not covered by the earlier
  parameter-only guard.
- State-changing PAPER and execution handlers now require POST, including
  legacy aliases. The authenticated GET mutation guard rejects those action
  paths before dispatch. `/risk/registry` and `/risk/registry/check` remain
  readable via GET but synchronize the Registry only when explicitly called
  with POST; responses report whether a sync was attempted and a sanitized
  error class when it failed.
- Focused auth/method tests: **80 passed**. Full guarded offline suite
  `tests/run_falcon_pilot_minimal_offline.py --extra`: **701 passed, 1
  skipped, 1 deselected** in **680.48s**, exit code 0. The runner blocks
  networking/DNS/URL opening, subprocess creation and `.env` reads before
  collection. Tests use synthetic requests/local state; no service endpoint
  was invoked.
- This is local Windows candidate evidence only, not proof of deployed behavior
  or readiness for LIVE. No AWS, Render, production, commit, deployment or
  trading action occurred. Production remains on base commit
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`; the candidate changes do not
  affect it until a separately validated, zero-cost deployment.

## Policy report GET side-effect closure — 2026-11-01

- A targeted AST scan of GET-capable Flask routes found two report endpoints
  that could trigger writes indirectly: auto-release report called the
  execution routine when no prior result existed, and priority report passed
  `commit=True`. The auto-release HTTP report now reads health/last-run state
  only; the priority report computes a `commit=False` preview. The separate
  policy-action endpoints remain blocked for GET by the authenticated method
  guard. Telegram's explicitly action-oriented helper was left unchanged.
- Focused HTTP/auth tests: **82 passed**. Final guarded offline suite
  `tests/run_falcon_pilot_minimal_offline.py --extra`: **703 passed, 1
  skipped, 1 deselected** in **654.16s**, exit code 0. The runner blocks
  network/DNS/URL access, subprocess creation and `.env` reads before test
  collection. A follow-up AST scan found remaining literal `commit=True`
  only on explicit policy action routes (GET blocked), dynamic Registry
  persistence guarded by mutation flags, and execution console/live code
  conditional on POST.
- Local Windows evidence only. No app endpoint, exchange, AWS, Render or
  production state was accessed or changed; no order, commit or deployment
  occurred. Production still runs the previously observed base release
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`.

## Current isolated exchange-adapter environment — 2026-11-01

- Revalidated the current local dependency state: `requirements.txt` specifies
  `ccxt==4.5.88`; the isolated offline interpreter imports exactly version
  4.5.88 from its local virtual environment. This supersedes older dated notes
  that observed an unpinned requirement/default interpreter without CCXT.
- Re-ran the two synthetic pinned-adapter tests and the fail-closed stop-order
  readback case with pytest plugin autoload disabled: **3 passed, 11
  deselected**. The tests exercise parser/request construction and synthetic
  responses only; no exchange connection, credential, or order was used.
- Pinning and adapter tests make the local candidate reproducible, but the
  authoritative BingX response for a live, untriggered `STOP_MARKET` still has
  not been observed. Keep stop confirmation fail-closed. No AWS, Render or
  production change was made.

## Synthetic broker-writer boundary regression — 2026-11-01

- Re-ran `test_broker_account_client_order_boundary_v1.py` together with
  `test_broker_managed_close_timeout_semantics_v1.py` in the isolated Python
  environment: **60 passed**. The boundary test's fixture temporarily enables
  the post-policy writer branch only for its fake exchange objects; it does
  not change `ENABLE_REAL_TRADING`, `BROKER_DRY_RUN`, or production flags.
- Both files are included in the guarded offline `--extra` runner, whose latest
  full result is **703 passed, 1 skipped, 1 deselected**. The runner blocks
  network/DNS/URL opening, subprocess creation and `.env` reads before test
  collection. This covers synthetic send-boundary/timeout behavior only; it
  does not send an exchange request or prove live stop readback.
- This supersedes the earlier exploratory run recorded in this evidence file
  that failed because fake-writer tests were still exercising the production
  default-off gate instead of installing an explicit test-only fake boundary.
  Live readiness remains unproven, and no external service or production
  setting was changed.

## Fresh personal-topology check and local lock/persistence regressions — 2026-11-01

- Re-listed services in the user-confirmed Render workspace. The only service
  remains `central-robos-bingx` (`srv-d8rtuv9o3t8c73ehav5g`), one Standard
  Python web-service instance running `python main.py`, with one 2 GB `/data`
  disk, `autoDeploy: no`, public ingress, and the same repository/branch.
- The latest deploy remains `dep-dbaooagm7kps739mcsqg`, status `live`, commit
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`, matching this worktree's base
  HEAD but not its dirty candidate. Thirty-five hourly `instance_count`
  samples from 2026-10-31 00:00 UTC through 2026-11-01 10:00 UTC were all 1.
- A filtered app-log query for `BOT CARREGADO`, `LOCK OK`, `LOCK ATIVO`, and
  `ERRO LOCK` returned no matching records. This does not prove there are no
  processes/writers: current PID/thread census, active loops, lock ownership,
  and effective production mode flags remain unverified. No environment
  values, disk contents, secrets, or Registry data were requested.
- Re-ran temporary-filesystem and source-level safety tests for runtime file
  locking, durable atomic Registry writes, persistent-storage readiness,
  bootstrap guards, and HTTP route protections: **128 passed** in 152.46 s.
  These tests use local temporary files and synthetic requests; this direct
  targeted invocation did not contact external services. The subsequent
  preview/update documentation regression plus auth suite passed **83 tests**;
  `py_compile` and `git diff --check` passed.
- The fresh topology still does not justify distributed C3 for personal use.
  Local evidence supports the simple single-instance/process-lock design, but
  active production writer/process behavior and effective PAPER/DRY_RUN flags
  are still not proven. No AWS/Render/production state was changed; no deploy,
  commit, or order occurred.

## Disaster-stop preview side-effect closure — 2026-11-01

- Static inspection of the currently deployed base commit confirms that
  `/disasterstopfallback` and `/disasterstop` accept GET directly. Their
  builder persists the latest result and appends an event even when
  `commit=false`; a public GET can therefore write persistent diagnostics.
  The GET path also calls the position/stop/Registry safety reader and includes
  that result in its response. The service has public ingress, and deployed
  `HEAD` contains no `personal_http_auth` hook. With explicit `commit=true`
  and an accepted acknowledgement, the route can also change the fallback
  lock based on the live position/safety read. This is an unauthenticated
  account-data exposure and persistent-state/availability risk, not proof
  that a real stop can be submitted: the base helper requires a reserved
  client-order ID before it calls the broker, while this route path supplies
  no reservation. Production mode flags and runtime behavior remain
  unverified.
- The isolated candidate now routes result persistence through
  `persist_disaster_stop_fallback_result_v1`: preview (`commit=false`) writes
  neither the latest file nor the event log; committed results still persist
  both. The route retains GET-preview plus authenticated JSON POST for
  commit, and GET with commit intent is rejected.
- Network-blocked route tests, including actual temporary-file assertions for
  preview-no-write and committed-write, passed with the personal HTTP/auth
  suite: **100 passed** in 178.97 s. `py_compile` and `git diff --check` passed.
- This is only a local candidate; production still runs base commit
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`. No endpoint was invoked and no
  production, AWS, Render, exchange, order, commit, or deploy state changed.

## BingX protective-stop acknowledgement plus exact-ID readback — 2026-11-01

- Reviewed the current official BingX Swap Trade and account-WebSocket
  references. The Place Order response schema includes `stopPrice`; the
  documented query/open-order/history and order-update schemas do not. The
  implementation therefore keeps exact trigger validation on the creation
  acknowledgement and requires a subsequent read-only exact-order-ID query to
  confirm the same active order's other material fields. Any returned trigger
  must still equal the requested value; absent or malformed creation evidence,
  conflicting/malformed query trigger, identity mismatch, inactive order, or
  semantic mismatch fails closed.
- New network-blocked regression selection: **100 passed in 44.14s** across
  `tests/test_falcon_client_order_id_collision_guard_v1.py`,
  `tests/test_broker_account_client_order_boundary_v1.py`,
  `tests/test_falcon_management_safety_v1.py`, and
  `tests/test_bingx_ccxt_stop_readback_contract_v1.py`. DNS, socket connects,
  and `urllib.request.urlopen` were blocked. Synthetic tests only; no exchange
  access or orders.
- After the change, the complete guarded offline suite
  `python -I tests/run_falcon_pilot_minimal_offline.py --extra` passed with
  **707 passed, 1 skipped, 1 deselected** in **618.31s**, exit code 0.
- This local change is not deployed. It does not convert API documentation into
  factual production evidence and does not authorize PAPER/DRY_RUN changes,
  LIVE, or orders. No external state changed.

## Render topology and readiness metadata refresh — 2026-11-01

- Reconfirmed workspace `My Workspace` (`tea-d8gnnuojo6nc73ep3lg0`) and service
  `central-robos-bingx` (`srv-d8rtuv9o3t8c73ehav5g`) through read-only Render
  MCP calls. Metadata reports one Standard Oregon web instance, `python main.py`,
  one persistent 2 GB `/data` disk, public subdomain enabled, ingress
  `0.0.0.0/0`, automatic deploy off, and empty `healthCheckPath`.
- The latest deploy remains `dep-dbaooagm7kps739mcsqg`, status `live`, commit
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`, from 2026-10-19; it equals the
  isolated worktree's base HEAD, not the local dirty candidate. Hourly
  `instance_count` samples from 2026-10-26 00:00 UTC through 2026-11-01 10:00
  UTC all reported one instance.
- Render's current docs say an empty HTTP health-check path leaves the default
  TCP probe; that checks whether the port accepts a connection, not app-level
  readiness. The docs also state a persistent disk disables zero-downtime
  deploys, so any future release requires an explicit interruption/recovery
  plan.
- No environment-variable names/values, logs, disk contents, or application
  routes were queried. No Render/AWS configuration, production data, trading
  state, deploy, commit, or order was changed.
- A separate narrowly filtered Render app-log query for `BOT CARREGADO`,
  `LOCK OK`, `LOCK ATIVO`, and `ERRO LOCK`, from 2026-10-25 through the current
  query time, returned zero matching records for each filter. This confirms
  there is no recent matching startup/lock log evidence available; it does not
  prove that bot threads/writers are inactive or enumerate live processes.
- Read-only source inspection of the deployed base commit confirms its
  `/disasterstopfallback` and `/disasterstop` routes accept unauthenticated GET
  and invoke the fallback builder. The current local candidate's global HTTP
  auth/method gate is not part of that deployed commit. No production route was
  called; the live exposure is inferred from the verified live commit plus its
  source.
- Revalidated the local authentication and fallback-route candidate with
  sockets, DNS, and `urllib.request.urlopen` blocked: **105 passed** across
  `tests/test_personal_http_auth_gate_v1.py`,
  `tests/test_disaster_stop_fallback_route_auth_v1.py`, and
  `tests/test_execution_engine_public_health_redaction_v1.py` in 190.53s.
  This is local-only evidence; it does not change the live deployment or prove
  Render environment credentials are configured.

## Full guarded offline suite after preview-write fix — 2026-11-01

- Re-ran `python -I tests/run_falcon_pilot_minimal_offline.py --extra` on the
  current candidate after the disaster-stop persistence change. Result:
  **707 passed, 1 skipped, 1 deselected** in **616.24 s**, exit code 0.
- The runner denies sockets, DNS/URL opens, subprocess creation, and `.env`
  reads before pytest collection. The selected extra suite covers personal
  HTTP auth/method restrictions, runtime locks, Registry atomic durability,
  entry/order boundaries, stop readback fail-closed behavior, disaster-stop
  routes, close handling, and reconciliation with synthetic/local state.
- This strengthens local candidate evidence only; it does not prove the
  production service has these changes, verify its environment flags, or
  establish live exchange behavior. No external endpoint, account, AWS,
  Render, production data, real order, commit, or deployment was touched.

## Personal HTTP auth regression rerun — 2026-11-01

- Re-ran `tests/test_personal_http_auth_gate_v1.py` with the offline project
  interpreter and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, **without** Python's
  `-I` isolated-import flag:
  `python -m pytest -x -q tests/test_personal_http_auth_gate_v1.py`.
- Result: **83 passed in 20.60 s**. The module's autouse fixture blocks socket
  connection and DNS APIs. The suite covers fail-closed Basic auth, all-route
  hook ordering, cross-site request denial, GET mutation rejection, and the
  seven bot clients' authenticated calls to the Central risk endpoint.
- An initial invocation with `python -I -m pytest` produced import failures
  because isolated mode excludes the repository from the module search path;
  this was a test-launcher issue, not a code change. The corrected invocation
  passed. No source code, secrets, network service, AWS, Render, production
  data, or trading state was accessed or changed.
- Separately re-ran `tests/test_disaster_stop_fallback_route_auth_v1.py` and
  `tests/test_execution_engine_public_health_redaction_v1.py` using the same
  offline interpreter and plugin setting. Result: **22 passed in 181.53 s**.
  The fallback suite explicitly blocks socket connect, connect_ex, DNS, and
  create_connection; the redaction suite uses source-isolated synthetic
  payloads. These checks validate local behavior only, not the deployed routes.

## Personal single-process preflight regression — 2026-11-01

- With socket connect/connect_ex, DNS, `create_connection`, and
  `urllib.request.urlopen` blocked before pytest collection,
  `tests/test_falcon_real_pilot_preflight_fail_closed_v1.py` passed **56
  tests in 15.35 s** using synthetic providers.
- The tests confirm that missing Registry process-lock availability remains a
  blocking storage-readiness failure. They also confirm that dormant
  distributed C3 coordination is only a non-blocking warning in the
  single-process personal preflight, while the preflight still reports
  `no_order_sent=true` and `sent=false`. This is intended policy/test evidence,
  not a production preflight result or authorization to trade.
- The runtime lock and atomic Registry persistence tests then ran with socket,
  DNS, and URL-open calls blocked before collection:
  `tests/test_runtime_file_lock_fail_closed_v1.py` plus
  `tests/test_trade_registry_atomic_durable_write_v1.py` passed **11 tests in
  95.87 s**. They use only pytest `tmp_path` directories and synthetic lock
  backends; no Render disk or production Registry was read or written.

## GET-side-effect gate follow-up — 2026-11-01

- Static inspection found `/memory/stabilizer` and its legacy alias
  `/memorystabilizer` are GET routes that can call GC and allocator trimming.
  Passing `gc=false` does not make them read-only because `_memory_cleanup`
  still collects when RSS exceeds its configured threshold.
- Added both paths to the local GET-mutation block list, enabled POST on the
  actual Flask route decorators, and added synthetic Flask plus AST regression
  coverage asserting GET is rejected while authenticated POST remains allowed.
- Re-ran `tests/test_personal_http_auth_gate_v1.py` with the offline
  interpreter and plugin autoload disabled. Latest result: **88 passed in
  24.10 s**;
  the module blocks socket and DNS APIs. This is local candidate evidence;
  no deployed route was invoked or changed.
- A static GET-handler scan found other state-intent fields such as
  `persist`, `record`, `save`, `force`, `commit`, and `send`; the auth gate's
  generic action-field filter blocks their affirmative query values. This
  scan is a triage aid, not proof that every GET handler is side-effect-free.

## Personal preflight and Registry durability rerun — 2026-11-01

- Ran `tests/test_falcon_real_pilot_preflight_fail_closed_v1.py`,
  `tests/test_trade_registry_live_entry_storage_readiness_v1.py`,
  `tests/test_runtime_file_lock_fail_closed_v1.py`, and
  `tests/test_trade_registry_atomic_durable_write_v1.py` together with the
  pinned offline interpreter. Before pytest collection, socket connect,
  connect_ex, DNS, `create_connection`, `sendto`, and `urllib.request.urlopen`
  were replaced with hard failures; plugin autoload was disabled.
- Result: **71 passed in 150.25 s**. The persistence tests use `tmp_path` and
  injected failures to prove atomic replace ordering, preservation of the
  previous file after file-fsync failure, and failure instead of false
  success after directory-fsync failure. Runtime-lock tests use temporary
  files and synthetic `fcntl` implementations.
- The personal preflight asserts local readiness behavior only: missing
  Registry process-lock availability blocks storage readiness; dormant C3 is
  advisory in the synthetic single-process case. It is not production
  startup, physical Render-disk durability, or trading readiness evidence.

## Entry, close and reconciliation regression follow-up — 2026-11-01

- A broader network-blocked run covering entry/client-order boundaries, close
  timeout behavior, Falcon safety/preflight, shadow HTTP, Registry readiness,
  disaster-stop routes, stop readback and reconciliation reached **476 passed**
  before reporting three failures in the final Registry-close fixtures. The
  failing fixtures called the guarded production `save_registry` to create a
  missing active file; that writer intentionally refuses to bootstrap a
  missing Registry, and Windows directory-fsync support is separately tested.
- Updated those test-only fixtures to seed only their isolated `tmp_path`
  Registry file, point the app's active data directory there, and inject a
  test-only atomic writer for reconciliation semantics. Durable write/failure
  behavior remains covered separately by the 11 passing lock/atomic tests
  recorded above; the injected writer is not durability evidence.
- After the fixture adjustment, the complete
  `tests/test_falcon_central_only_reconciliation.py` module passed **39 tests
  in 23.20 s** with socket connect/connect_ex, DNS and URL-open blocked before
  collection. The adjusted GET mutation-filter case passed **1 test in 2.29 s**
  under the same network block. The entire original 15-file set has not yet
  been rerun end-to-end after these test-only adjustments.
- `git diff --check` passed. The application code was not changed in this
  follow-up; no secrets, exchange, AWS, Render, production data, commits,
  deployments or real orders were accessed or changed.

## Position, fill, stop-containment and close rerun — 2026-11-01

- Ran seven focused modules covering Falcon position ownership limits,
  partial-capable execution/fill handling, main account client-order
  integration, main LIVE preflight guard, initial-stop failure containment,
  disaster-stop failure forensics, and real-close reconciliation v11.
- Before collection, the offline runner blocked socket connect/connect_ex, DNS,
  `urllib.request.urlopen`, and urllib3 connection creation. Result:
  **463 passed in 254.04 s**. These use local fixtures/synthetic exchange
  responses; no exchange account, live order, or deployed runtime was tested.
- This adds local regression evidence for position/fill/close control paths,
  but does not clear the production gates: current deployed release, live
  account position/stop state, recent preflight, and production persistence
  remain unverified here.

## Complete 15-module rerun after fixture corrections — 2026-11-01

- Re-ran all 15 modules listed in the earlier Entry/close section together,
  after correcting the mutation-GET contract expectation and Registry-close
  test setup. The pre-collection wrapper hard-blocked socket connect,
  connect_ex, DNS, `urllib.request.urlopen`, and urllib3 connection creation.
- Result: **479 passed in 521.50 s**, exit code 0. This supersedes the earlier
  partial 476-pass/3-fixture-failure aggregate. The separate Registry durability
  tests continue to provide the atomic/fsync evidence; reconciliation tests
  inject only a temporary semantic writer.
- `git diff --check` passed. This remains local synthetic evidence; no real
  exchange, order, AWS, Render, production data, secret, commit, or deploy was
  involved.

## PAPER/DRY_RUN and HTTP authorization rerun — 2026-11-01

- Ran `tests/test_trading_mode_defaults_fail_closed_v1.py`,
  `tests/test_personal_http_auth_gate_v1.py`, and
  `tests/test_auto_real_execution_bridge_route_auth_v1.py` together with
  socket connect/connect_ex, DNS, URL-open, and urllib3 connection APIs blocked
  before collection.
- Result: **106 passed in 60.70 s**. This covers local default-off trading
  controls, the personal HTTP authentication/GET-mutation gate, and the
  auto-execution bridge request boundary with synthetic inputs. It does not
  prove Render environment configuration or deployed authorization behavior.

## Full offline runner safety and rerun — 2026-11-01

- Inspection showed `tests/run_falcon_pilot_minimal_offline.py --extra` includes
  tests that import `main.py`, despite the old docstring claiming the runner
  would not import it. Its initial run used the application's default runtime
  auto-start setting and spawned runtime threads; Python terminated that
  attempt with a Windows fatal exception. That attempt is not valid test
  evidence. No network access or exchange activity was possible under the
  runner's guards; no orders were sent.
- Before rerunning, updated the offline test harness to set
  `CENTRAL_AUTO_START_RUNTIME=false` before importing pytest/collecting tests,
  and corrected its docstring. This is a test-runner-only setting; application
  defaults were not changed. The test-only `--extra` run then completed with
  **712 passed, 1 skipped, 1 deselected in 627.53 s**, exit code 0, with
  network, subprocess/process-launch, and `.env` access blocked by the runner.
- Runtime-data caveat: timestamps/sizes for five files under `data/` advanced
  during the validation window relative to the pre-run baseline. Current
  observed values are: `central_runtime_state.json` 591 bytes;
  `central_runtime_events.jsonl` 11,373 bytes;
  `trade_lifecycle_shadow_runtime_state.json` 249 bytes;
  `trade_lifecycle_shadow_events.jsonl` 21,500 bytes; and
  `trade_lifecycle_shadow_runtime_events.jsonl` 3,619,663 bytes (all last
  written between 08:46 and 08:48 local time). Their contents were not
  inspected or restored, to preserve user data. Therefore the run confirms
  offline test success but does **not** establish that the test suite leaves
  the working `data/` directory untouched or that all persistence tests use
  only temporary storage. Dedicated atomic/fsync tests above do use `tmp_path`.
- Final checks: branch remains detached `HEAD` at
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`; tracked user modifications remain
  present; `git diff --check` passed. No commit, push, deploy, AWS/Render write,
  production mutation, secret access, or real order occurred.

## Offline test data isolation and current Render read-only check — 2026-11-01

- The previous full test run changed timestamps and sizes under the checkout's
  `data/` directory. To prevent repeating that, the offline runner now creates
  a per-process temporary directory and directs `CENTRAL_DATA_DIR`, `DATA_DIR`,
  `TRADE_REGISTRY_FILE`, and `TRADE_LIFECYCLE_SHADOW_DATA_DIR` there before
  pytest collection. It still disables runtime autostart and denies network,
  subprocess/process-launch, and `.env` file access.
- Re-ran `..\.offline-envs\cq-ccxt-4.5.88\Scripts\python.exe -I
  .\tests\run_falcon_pilot_minimal_offline.py --extra`: **712 passed, 1
  skipped, 1 deselected in 690.06 s**, exit code 0. The five previously
  changed runtime/shadow files kept exactly the same sizes and last-write
  timestamps throughout this isolated rerun. This supports that the harness
  no longer writes those configured runtime files; it is still not evidence
  about every arbitrary relative-path write in every test.
- Read-only Render MCP inspection in the confirmed `Central Quant` account and
  workspace found service `srv-d8rtuv9o3t8c73ehav5g` on branch
  `codex/c3-final-release-promote-20260910`, one Standard instance, attached
  `/data` disk (2 GB), public IP allowlist `0.0.0.0/0`, and auto-deploy off.
  Latest deploy is `dep-dbaooagm7kps739mcsqg`, status `live`, commit
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1` (2026-10-19). The known local
  authenticated disaster-stop boundary is therefore not in the live release.
- Read-only inspection of `git show HEAD:main.py` (the exact source commit
  reported live by Render) confirms the deploy has no global
  `central_personal_http_auth_before_request` hook. Its `/disasterstopfallback`
  and `/disasterstop` routes are GET-only and pass the query parameter
  `commit=true` directly into the fallback builder, with no route
  authentication (the builder still applies its internal safety checks).
  Combined with public ingress, this is a concrete unauthenticated path to the
  order-capable fallback handler in the deployed source. No request was made
  to either route. The dirty local
  source instead uses preview-only GET and requires authenticated POST with
  explicit JSON commit/ack; its offline route tests pass.
- A read-only AST scan of that same deployed `HEAD:main.py` counted 821
  GET-capable route decorators (aliases included). It found 34 GET-capable
  handlers directly reading query keys associated with mutation intent, such
  as `commit`, `persist`, `repair`, `execute`, `send`, `save`, or `confirm`.
  This is a static triage count, not proof that all 34 handlers mutate state;
  it shows the exposure is broader than the disaster-stop aliases. The local
  before-request auth and GET-mutation gates are designed to cover the whole
  Flask app, and their offline route tests pass, but those gates are absent
  from the live source commit.
- A read-only Render request-log query for `/disasterstopfallback` and
  `/disasterstop` failed with service response 503 (“log retrieval is currently
  unavailable”). We cannot infer whether either endpoint was used.
- The available Render MCP exposes no read-only environment-variable listing
  tool. A computer-use attempt to inspect only the three non-secret trading
  flags in the dashboard failed to activate the selected Chrome window twice;
  no dashboard action or setting change occurred. Consequently the deployed
  values of `ENABLE_REAL_TRADING`, `BROKER_DRY_RUN`, and `FALCON_MODE` remain
  unverified. Manual read-only check is required in the Render dashboard; do
  not reveal or share any other environment-variable values.
- No AWS/Render/production mutation, deploy, credential/secret access, commit,
  push, or order was performed. Because the personal-use audit has not shown a
  concrete need for distributed C3, the C3-conditional external-write
  authorization does not apply; the local route fix remains undeployed. This
  is a stop condition for any LIVE-readiness claim. The deployed trading-mode
  environment values still require read-only verification without exposing
  secrets.
- Final `git diff --check` passed. Checkout remains detached `HEAD` at
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`; existing tracked changes remain
  intact.

## GET notification-intent hardening — 2026-11-01

- The deployed-source AST triage found `/trendpro/daily_summary` reads
  `send=true` alongside `confirm=true` to send a Telegram summary. The global
  GET gate already blocks affirmative `confirm`, so the handler could not send
  with only `send=true`; nevertheless, added `send` to the generic action
  fields so affirmative send intent is independently rejected over GET.
- Added `send=true` to the existing parameterized authenticated-GET regression
  test. The affected files were untracked user files before this edit and were
  preserved in place.
- An initial ad hoc test invocation produced harness-only failures because it
  replaced `subprocess.Popen` with a plain function, breaking Flask/Python
  imports. Corrected the test harness to block process creation with a
  `Popen` subclass, while keeping network, `.env`, and runtime-autostart guards.
  The complete `tests/test_personal_http_auth_gate_v1.py` module then passed:
  **89 passed in 22.83 s**.
- The five previously changed runtime/shadow files retained the same sizes
  and last-write timestamps as before this focused test. `git diff --check`
  passed; no AWS/Render/production change, deploy, commit, secret access, or
  real order occurred.

## GET action-field coverage audit — 2026-11-01

- Added a dynamic parameterized test that reads the guard's configured
  `action_fields` set and asserts every affirmative field value is blocked on
  a synthetic GET route. This prevents future additions to the guard's field
  set from silently escaping regression coverage. Existing targeted integration
  cases also exercise `send=true` through Flask's actual request hooks.
- Ran the targeted offline selection
  `every_configured_action_field or additional_action_intent_fields` from
  `tests/test_personal_http_auth_gate_v1.py`: **37 passed, 82 deselected in
  19.50 s**. The harness blocked network, subprocess/process creation and
  `.env` reads; runtime auto-start was disabled and data paths were temporary.
- This proves the configured parameter list fails closed in the helper and
  selected Flask-hook cases; it does not prove that the entire monolithic
  application or deployed Render release is safe. No external changes or
  orders occurred.

## Fresh focused personal-safety validation — 2026-11-01

- Revalidated the checkout before continuing: detached `HEAD` at
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`, with existing tracked changes
  and untracked candidate/report files preserved. No source or configuration
  was edited during this validation.
- Used the installed interpreter at
  `C:\Users\giuli\AppData\Local\Python\bin\python.exe`; the WindowsApps
  `python.exe` alias could not be started in this environment. No packages
  were installed and no network access was enabled.
- Loaded the repository's offline test boundary before collection. It blocks
  sockets/network, subprocess creation, `.env` reads, runtime autostart, and
  directs Registry/shadow data paths to a temporary directory. Focused suites
  covered the personal HTTP auth/method gate, auto-real bridge route auth,
  disaster-stop fallback route auth, trading-mode fail-closed defaults, and
  execution-engine health redaction: **159 passed in 273.24 seconds**, exit
  code 0.
- Fresh read-only Render service/deploy inspection still reports one Standard
  instance, `python main.py`, a 2 GB `/data` disk, public ingress, and
  `autoDeploy: no`. Latest live deploy remains
  `dep-dbaooagm7kps739mcsqg` at base commit
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1` from 2026-10-19. No environment
  variable values or secrets were queried; the connected Render toolset has
  service metadata and environment-update tools, but no environment-value
  read tool.
- `git diff --check` passed. No AWS/Render/production mutation, deploy, commit,
  secret access, or real order occurred. Local candidate safeguards remain
  undeployed and production trading-mode flags remain unverified.

## Learning outcome GET-write closure — 2026-11-01

- A static AST inventory of the local Flask source found 169 GET-capable
  handlers reading 108 distinct query fields. Manual review distinguished
  identifiers/data fields from mutation intent. A real finding was confirmed:
  the deployed base commit registers `/learning/outcome/v1`,
  `/learning/result/v1`, and `/learn/outcome/v1` for GET and POST, while the
  handler calls `build_learning_outcome_v1`; for a valid outcome that builder
  appends an OUTCOME record to its event log. This is an unintended GET write,
  independent of the separate global HTTP-auth requirement.
- No internal repository call sites to those aliases were found. Changed the
  local candidate routes to POST-only and added all three aliases to the
  authenticated-GET mutation block as defense in depth. The regression test
  verifies the route methods are POST-only, and the Flask-hook test verifies
  authenticated GETs to each alias return 405 without invoking the synthetic
  writer. POST behavior is left available.
- After the edit, the full
  `tests/test_personal_http_auth_gate_v1.py` suite passed: **123 passed in
  19.91 seconds**. The offline runner blocked network, subprocesses and `.env`
  reads, disabled runtime autostart, and directed mutable Registry/shadow paths
  to a temporary directory. `git diff --check` passed.
- This is a local candidate fix only. The live Render base still registers
  these GET aliases and has no global auth hook; no request was made and no
  external state, deploy, commit, secret, or order was touched.

## GET-triggered Registry sync confirmation closure — 2026-11-01

- Further static handler review found that `/traderegistry/sync/confirm`,
  `/trade_registry/sync/confirm`, and `/trades/sync/confirm` set
  `path_confirm=True` solely from the URL suffix. A GET to any alias therefore
  commits a Registry sync even without `confirm=1`. The ordinary sync aliases
  with `?confirm=1` were already blocked by the generic affirmative `confirm`
  query-field gate; the bare `/confirm` aliases were not.
- Changed the three confirmation aliases to POST-only and added them as
  explicit GET-mutation paths. Added regression checks for the six route
  methods and for authenticated GETs to all three bare confirmation URLs being
  rejected before the synthetic writer runs. The ordinary sync preview aliases
  remain GET/POST; the underlying sync handler was not otherwise changed.
- After both the Learning Outcome and Registry Sync fixes, the full
  `tests/test_personal_http_auth_gate_v1.py` suite passed: **127 passed in
  21.66 seconds**. Network, subprocess, `.env`, and runtime-autostart guards
  were active, with data paths isolated to a temporary directory.
- Both findings exist in the deployed base source (`HEAD` before these local
  edits). The fixes remain local and undeployed. `git diff --check` passed;
  no service, Registry data, credential, secret, commit, or order was changed.
- Follow-up source search found no other handler deriving confirmation solely
  from a `/confirm` path suffix. The GET endpoints `/realpnlr`,
  `/realpnlr/text`, and `/adaptive/build` also default their commit flag to
  true, but the HTTP GET guard explicitly requires `commit=false` for those
  paths; regression cases for those documented read-only modes passed in the
  same full gate suite. This narrow search does not certify every GET handler
  or every transitive side effect in the monolithic app.

## Destructive history rebuild route disabled — 2026-11-01

- Continued the AST triage of GET-capable Flask handlers and followed the
  `/history/trades/rebuild` route into
  `history_manager.rebuild_closed_trades_v4_from_events`. That function backs
  up `closed_trades.jsonl`, truncates the active file, then rewrites it from
  events. This is a bulk historical rewrite and is prohibited by the personal
  readiness goal; no endpoint was invoked.
- The route is now POST-only and inert: even POST returns
  `DESTRUCTIVE_HISTORY_REBUILD_DISABLED` without importing/calling the history
  manager. The global GET mutation guard also rejects GET for this path. Added
  a source-level regression that executes the isolated handler and verifies
  the 409/no-write response, plus an authenticated-GET guard case.
- The complete bounded offline safety runner
  `tests/run_falcon_pilot_minimal_offline.py` passed: **313 passed in 374.79 s**,
  exit code 0. It includes the HTTP auth/method regression suite and the new
  inert-handler test. Network, subprocess, `.env`, and runtime-autostart guards
  were active; mutable data paths were isolated to a temporary directory.
- `git diff --check` passed. This remains a local, undeployed candidate. No
  history file, production service, Registry, secret, AWS/Render resource,
  commit, or order was changed.

## Fresh Render release metadata — 2026-11-01

- Read-only `get_service` and `list_deploys(limit=1)` were run in the confirmed
  `My Workspace` (`tea-d8gnnuojo6nc73ep3lg0`). Service
  `central-robos-bingx` (`srv-d8rtuv9o3t8c73ehav5g`) remains a Standard Python
  web service in Oregon, one configured instance, start command `python
  main.py`, 2 GB persistent `/data` disk, public subdomain and ingress
  `0.0.0.0/0`, empty HTTP health-check path, and automatic deploy disabled.
- Latest deploy remains `dep-dbaooagm7kps739mcsqg`, status `live`, at commit
  `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1` from 2026-10-19. The commit
  matches the local base and still contains the GET history-rebuild route;
  local fixes remain undeployed.
- No environment variables or values, logs, disk data, secrets, or application
  endpoints were read or invoked. No Render/AWS state was changed. A deploy's
  zero-cost condition is not established, and the persistent disk implies an
  interruption during deployment.

## Official BingX stop client-ID constraint — 2026-11-01

- The current official Swap Trade reference states that `clientOrderId` on the
  real Place Order endpoint is supported for `MARKET` and `LIMIT` only. The
  separate test endpoint's parameter table is not evidence that a real
  `STOP_MARKET` accepts the field; its documentation warns that test-order
  success does not guarantee real-order acceptance.
- Source: [BingX official Swap Trade API reference](https://github.com/BingX-API/api-ai-skills/blob/main/skills/swap-trade/api-reference.md),
  Place Order parameters and response schema.
- The local initial disaster-stop path explicitly calls the reserved-order
  helper with `exchange_client_order_id_supported=False`. It strips the
  unsupported client ID from the exchange request, then validates the
  exchange-generated order ID and reads that exact order back. This matches
  the documented constraint; do not change it to send a client ID on a real
  STOP_MARKET request based on the test endpoint.
- The official reference documents the creation response's system order ID
  and trigger price. Local offline adapter/readback tests use synthetic
  responses only; no live BingX behavior, account, credentials, or order was
  queried. This resolves the local API-contract question, but is not evidence
  of production readiness or permission to trade LIVE.
- No code change was needed. Existing dirty/untracked work was preserved; no
  commit, deploy, AWS/Render mutation, or secret access occurred.

## History-rotation commit method correction — 2026-11-01

- A fresh expanded offline run found one failure in the Flask integration test:
  its synthetic `add_url_rule` call passed an endpoint name as the view
  function, so POST raised `TypeError` instead of reaching the test writer.
  The same review showed both real history-rotation commit routes still
  declared `GET`, even though their handlers call file-rotation commit logic.
- Changed `/history/rotation/commit/text` and
  `/history/rotation/emergency/commit/text` to accept `POST` only. Fixed the
  synthetic Flask route registration and updated source-contract assertions.
  The shared HTTP guard continues to reject GET on these action paths.
- Network-blocked focused rerun of `test_personal_http_auth_gate_v1.py` and
  `test_history_events_rotation_v1.py`: **174 passed** in 57.69 seconds, exit
  code 0. The offline guard blocked network, subprocess, `.env` access and
  runtime auto-start; the tests use synthetic requests/data.
- Before correction, the expanded suite was **751 passed, 1 failed, 1 skipped,
  1 deselected**; the failure is the now-fixed fixture/route-method contract.
- After correction, the complete offline expanded runner
  `python -I tests/run_falcon_pilot_minimal_offline.py --extra` passed:
  **752 passed, 1 skipped, 1 deselected** in **630.23 seconds**, exit code 0.
  The skip is a platform capability test; the deselected case requires a
  subprocess and is outside the network/process-denied runner. No history file
  was rotated, and no external service, account, secret, commit, deploy, or
  order was touched.

## Remaining production-configuration and POSIX evidence limits — 2026-11-01

- Render connector capability inspection found service/deploy metadata and an
  environment-variable update operation, but no read-only operation to fetch
  only selected existing variable values. I did not use log search or a full
  environment listing as a workaround because those could expose unrelated
  secrets. The Render dashboard's Environment view remains the manual source
  for confirming only `ENABLE_REAL_TRADING`, `BROKER_DRY_RUN`, and
  `FALCON_MODE`; do not copy or send any other values. The official docs warn
  that saving environment changes can trigger deployment; no setting was
  changed here.
- The local WSL inventory command returned `Wsl/E_ACCESSDENIED`. Therefore this
  Windows host cannot currently provide POSIX/`flock` execution evidence.
  Windows offline suite results do not prove Linux file-lock semantics on
  Render. No WSL distro or container was installed or changed.
- Sources: [Render Environment Variables and Secrets docs](https://render.com/docs/configure-environment-variables)
  and the connector's available read/update operations. Production flag
  values and deployed runtime process state remain unverified.

## Learning refresh GET write closure — 2026-11-01

- Static review followed the `/learning/refresh` GET handler into
  `learning_engine.refresh_state`, which appends a `LEARNING_STATE_REFRESH`
  record to the audit JSONL. Although it does not change trading policy or
  orders, it is a persistent side effect reachable by GET. No internal callers
  of this HTTP route were found.
- Changed `/learning/refresh` to POST-only and added it to the explicit GET
  mutation-path deny list. Added an integration regression proving authenticated
  GET returns 405 without invoking the synthetic writer while authenticated
  POST remains usable. Updated the existing route contract test.
- Focused network/process/`.env`-blocked run of
  `test_personal_http_auth_gate_v1.py` and
  `test_automatic_learning_refresh.py`: **157 passed** in **148.92 seconds**,
  exit code 0.
- Complete expanded offline runner after the change:
  `python -I tests/run_falcon_pilot_minimal_offline.py --extra` —
  **753 passed, 1 skipped, 1 deselected** in **650.68 seconds**, exit code 0.
  The same temporary data isolation, socket/DNS/URL and process-launch blocks,
  `.env` denial, and runtime-autostart disable were active. The skip/deselect
  are platform/process-boundary limits, not passing POSIX evidence.
- No learning audit or Registry data was modified by the tests; no external
  service, secret, commit, deploy, or trading order was accessed or changed.

## Final worktree integrity check for this local pass — 2026-11-01

- Worktree remains detached at `0ecced0d3088e124d9a84d8e8c5afaf35871a0a1`.
  The existing tracked modifications and untracked candidate files were
  preserved; this pass created no commit and changed no branch or history.
- `git diff --check` passed after the route-method and test changes. No AWS,
  Render, production, credential, secret, or exchange operation occurred.

## Isolated cross-process idempotency test — 2026-11-01

- Inspected `test_shadow_validation_append_is_idempotent_across_processes`:
  it launches two local Python subprocesses that call the shadow adapter's
  append-once helper against pytest's temporary directory. The child script
  contains no network clients or operational Registry access.
- The adapter serializes the append with a local file lock, rereads the
  temporary JSONL journal while holding that lock, and writes only if the
  synthetic event id is absent.
- Isolated execution with the pinned offline Python environment:
  **1 passed** in **0.70 seconds**. Both subprocesses completed and the test
  observed one synthetic event row. This is Windows local-filesystem evidence;
  it does not establish POSIX/Render disk durability or production readiness.
- Test scope was limited to the test's temporary directory. No network,
  AWS, Render, production, secrets, Registry data, or trading orders were used.

## Disaster-stop route guard regression rerun — 2026-11-01

- Re-ran `tests/test_disaster_stop_fallback_route_auth_v1.py` in isolation
  using the pinned offline Python environment: **17 passed** in **159.33
  seconds**. The suite uses a synthetic Flask request context and a stubbed
  builder; it verifies GET cannot commit, POST requires authentication and an
  explicit body acknowledgement, and invalid auth sources fail closed.
- The suite's autouse fixture blocks socket `connect`, `connect_ex`,
  `create_connection`, and DNS lookup for the test process. Tests use synthetic
  request/builder paths and do not invoke Render, AWS, the broker, or exchange
  APIs.
- The deployed base release remains unchanged and still contains the older
  unauthenticated GET mutation route. The local fix is not deployed. Treat
  production exposure as unresolved; do not invoke or share a GET URL with
  `commit=true`.
