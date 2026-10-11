# Milestone 1 report — 2026-10-11

Status: IMPLEMENTED SCAFFOLD / NOT ACCEPTED. Milestone 2 not started.

## Delivered
ARCHITECTURE.md and IMPLEMENTATION_PLAN.md precede implementation. Relational schema blueprint includes all requested entities, bundle revisions, evidence, processed membership and publication outbox. Narrow Playwright PoC interface includes manual login, exact one-source identity verification, visible timeline snapshot, known attachment metadata, supervised attachment download, local evidence and redacted event logging. No business processing/checkpoint is implemented in M1.

Selected source title: `ĐỐI CHIẾU KL- KẾ TOÁN IJC`.
Second supplied title reserved for later: `TDC-ĐỐI CHIẾU KL BÊ TÔN`.
User supplied reference: https://zalo.me/g/ovdqkwddcx2sgvgggy0n . Its association with the first title must be verified manually; invitation token is not a conversation ID. Agent must not join a group automatically.

## Executed validation
`PYTHONPATH=src python -m unittest discover -s tests -v`: 17/17 passed on Python 3.12.14, Linux.
`python -m compileall -q src`: passed.
Schema executed in an in-memory SQLite database; foreign keys enabled, active-revision unique index rejects double activation and foreign_key_check clean. Fake DOM and download tests verify fail-closed controls, mixed attachment capture, successful bytes, timeout/error handling, empty download rejection and no overwrite. These are contract/unit tests, not live-browser/network evidence.

## Outstanding acceptance gates
- Actual Zalo selectors/data extraction not observed: example contract attributes are NOT asserted to exist in Zalo.
- Automated search, timeline scrolling/backfill and complete attachment coverage require a verified live adapter; current PoC only handles an already visible configured source and visible messages.
- No real manual-login/browser/download run performed; Playwright browser installation and Windows execution not validated.
- No live network audit proving absence of forbidden Zalo mutations. Reading may mark conversations read as a platform side effect.
- SHA-256 exists in runner, but corrupt-file format validation remains pending for actual sample attachments.
- Exact group ID, fixture ground truth and link/title association not verified.
- Earlier GitHub 404/proxy failures resolved on 2026-10-11: official repository is accessible with push permission. Remote initial commit retained; architecture and PoC commits prepared on main. Remote publication is verified separately after push.

## Live operator procedure
Verify repository access through the connected GitHub account. On the Windows machine install dependencies/browser, manually inspect DOM and adapt the centralized adapter contract, configure exact source ID/title without secrets. Use an existing membership; do not auto-join. Prepare a labeled bounded timeline with mixed attachments and expected counts. Run PoC, compare local timeline manifest to ground truth, select one attachment and compare downloaded bytes/hash to known evidence. Exercise security/logout/drift and duplicate-title cases; locally audit permitted interactions and network behavior without recording credentials. Record Windows/browser/Zalo versions, dataset coverage, counts, checksums, failures and approval. Until all M1 gates pass, no M2 implementation.

## Live connectivity preflight — 2026-10-11 12:33 (Asia/Saigon)
Requested actual Zalo verification against the supplied allowlisted group reference. Ran HTTPS connectivity probe using the inherited environment proxy: `curl -I --max-time 20 https://chat.zalo.me`. Result: HTTP 403 from the proxy, curl exit 56 (`CONNECT tunnel failed`). This is a destination-access failure before Zalo content is reached, not a Zalo account rejection. Runtime policy snapshot contains no Zalo hosts and reports policy state unknown; do not infer access readiness.

Playwright and Chromium are available, but no interactive display and no Zalo persistent profile exist. No login, QR, timeline, source identity or attachment was accessed. No credentials were requested or recorded. No network-policy bypass was attempted. Live Milestone 1 remains BLOCKED / NOT ACCEPTED; all prior automated checks remain contract tests only.

### Required environment setup to resume
Use the environment configuration workflow to authorize `chat.zalo.me` and `zalo.me`; actual login, static-resource and attachment hosts must be identified and authorized as encountered, without broad blind wildcard access. Provide an interactive browser for manual login, or run the supervised PoC on the user's Windows machine with its own session. Never transfer cookies, browser profile, OTP or session credentials into GitHub/chat. User handles QR/security challenges manually. Verify whether the supplied invitation link corresponds to the first or second title and capture the actual conversation ID. Then inspect real DOM, implement centralized selector mapping, validate search/scroll/coverage, and execute the live acceptance procedure above. Domain access alone does not resolve missing login or DOM validation.

## User-observed Windows login — 2026-10-11
User supplied a screenshot showing Python 3.12.10, successful dependency/Chromium installation, the manual login launcher waiting for Enter, and authenticated Zalo Web with the configured group title visible. This establishes user-observed Windows manual login and navigation by title; it does not establish a stable conversation ID, agent-driven allowlist resolution, automated timeline coverage, attachment download integrity or absence of forbidden interactions. No screenshot or chat contents were stored in this public repository.

A fresh executor HTTPS probe still returns proxy HTTP 403 for chat.zalo.me. The authenticated browser is on the user's Windows machine, not connected to the executor. Keep the browser open during manual DOM inspection. Capture only the group-header DOM structure and one allowed message structure, excluding other conversations, credential/session values and signed download URLs. Verify actual selectors and identity before running the capture adapter. M1 remains NOT ACCEPTED pending these live integration gates.

## User-observed DOM samples — 2026-10-11
Screenshots establish conversation list rows with data-id=div_TabMsg_ThrdChItem, anim-data-id candidate group identity, selected .conv-item, and title under .conv-item-title__name .truncate. NBSP normalization is required for comparison. Received text is observed under data-id=div_ReceivedMsg_Text and data-component=message-text-content. A text container's ID suffix agrees with the candidate group ID; this does not prove ID stability across sessions.

Recorded a partial DOM profile in config/zalo.observed-dom.json; it is deliberately not a runnable selector configuration. Sender/time/message root, header identity, security detection and image/file/download controls remain unknown. Added a manual DevTools structure probe for a selected allowed message or image. It reads DOM only, guards the currently selected title/candidate ID, excludes sidebar/composer selection, emits ancestor tag/approved attributes only and never reads cookies/storage/image URLs/text. The actual scope of the selected element is operator verified; it is not a production allowlist boundary or successful timeline capture. No screenshots or message content were added to the public repository. M1 still NOT ACCEPTED.
