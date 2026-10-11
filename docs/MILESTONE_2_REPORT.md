# Milestone 2 — Delivery Bundle Engine

Status: ACCEPTED IN REDUCED PROPOSAL-GENERATION SCOPE, 2026-10-11 (Asia/Saigon). The user later waived per-image manual review and authorized M3. This does not verify any proposal or delivery. M1 was accepted under the user-approved reduced scope; user subsequently observed RAW captures in Firestore. Those observations do not independently validate the new M2 code.

## Implemented behavior

The browser read port now emits interleaved rendered DOM order for allowed text/image containers. This is layout order, not an inferred server timestamp or historical cursor. Album containers share a bubble rank so ten images in one album do not look ten times farther from a description. Full original message bodies remain alongside all evidence IDs; date/material/project/quantity/unit text is not replaced with a summary or converted into accounting values.

The deterministic versioned Engine proposes links in both directions within four rendered bubble positions, or within the same observed bubble. Proximity contributes a bounded score; a displayed sender match/mismatch can adjust it. Each link stores score contributions, direction, missing document/business evidence and all competing candidates. Document number/project/material/date/quantity matches are not fabricated from unseen image bytes. No rule reaches automatic-processing confidence; all proposals require review. Missing order produces no proximity link, cross-source evidence and duplicate/truncated capture records stop grouping, distant images stay orphaned, and selected attachments remain empty until an explicit review. A text containing several deliveries is preserved whole and remains a candidate, not an automatically parsed single verified delivery.

Local UI displays original text, candidate choices for each image, and competing alternatives. The operator may assign individual album images to different messages, merge follow-up messages into a direct main message, or split that merge in a later review. Each review requires a reason and exact capture/review version. Unknown identities, duplicate attachment assignments, unsupported cross-window choices and cyclic/chained message merges are rejected. The local-origin authenticated review endpoint is not an MCP tool or a Zalo mutation. Source text is rendered with textContent, never interpreted as HTML/scripts.

Each read commits its RAW capture and at most 200 bundle draft revisions atomically in one create-only Firestore commit. Capture membership/candidate links live in reportJson; queryable bundle documents under tenants/default/bundleRevisions contain captureId, provisional bundleId, sourceId, rulesetVersion, reviewVersion, state, accountingActive=false and proposalJson. A reviewed snapshot creates a new immutable capture/revision set with parentCapturePath and the review reason/assignments; old versions stay intact. Verified receipt includes bundleRevisionPaths. Same-operation retries preserve document IDs and recover a lost ACK by verifying the capture payload; atomic commit means the associated bundle writes are all present or absent. Limits reject oversize captures rather than silently truncating. No local business files, final checkpoints or accounting entries are written.

## Validation

87/87 automated tests passed with the pinned real 9Router bootstrap test enabled. Fourteen Engine cases cover image-before/image-after description, competing deliveries/projects, original multi-project quantity text, missing order, same-bubble uncertainty, album grouping, source mixing, truncation/duplicates, distant images, per-image review, invalid assignments, unresolved follow-up, merge/split audit and cyclic merge rejection, plus optional sender scoring. Other checks exercise actual Chromium DOM order and review UI including script-looking source text, REST atomic multi-document commit, authenticated local review, stale/invalid review rejection, cloud failure/no local fallback, MCP and prior M1 integrations. Existing dependency deprecation/settings warnings did not fail tests.

These tests use synthetic source labels/quantities and mocked Firestore REST. The executor proxy previously denied Firestore and Zalo access; no repeated live capture or remote deployment claim is made. No private uploaded chat/report content was added to the repository.

## Windows live acceptance procedure

1. Stop Agent with Ctrl+C, update official main ZIP over the source directory, restart `.venv\Scripts\python.exe -m material_agent.local_agent`.
2. Manually open the allowed group and connect. Use a bounded rendered sequence with known ground truth: one description and photos before/after it; also include a nearby second delivery to check competing candidates. No automated backfill/scroll is added.
3. Click “Đọc tin nhắn đang hiển thị”. Confirm verified cloud receipt, the M2 summary and all original dates/materials/projects/quantities/units in the message details. Check proposals against the actual Zalo sequence; uncertainty must stay unselected.
4. Select image-to-message associations and optionally merge a follow-up using its message selector. Enter a review reason, save, confirm reviewVersion increments and the new receipt. Try splitting the merge again. Leave unrelated/unreadable images unassigned.
5. In Firebase inspect tenants/default/captures and tenants/default/bundleRevisions; verify originalTexts, selected/proposed IDs, parent capture/audit chain and accountingActive=false. Repeated stale review must be rejected. Confirm no new local capture/log file.
6. Record the ground-truth comparison, image-before/image-after and competing case outcomes. Only then accept M2 and proceed to M3.

## Remaining boundaries

- Full document/OCR extraction and slip confirmation date (DD/MM/YYYY only) remain M4; no chat timestamp substitutes for that date.
- Images are identified as DOM metadata; no preview byte export, original download, Storage upload or original-image hash is added. The operator compares images in the open Zalo browser.
- The Engine handles current rendered capture windows, not complete history. DOM identities/bundle IDs are provisional until stable-source and cross-capture recovery design in M3. Re-reading creates another immutable candidate snapshot, not a deduplicated accounting delivery.
- Review session uses RAM and cloud snapshots. Reload/restart requires another read; reopening cloud review sessions, durable job leases and multi-device fencing are M3/cloud foundation work.
- Firestore still uses the user's public rules; actor identifies a local paired session, not an authenticated Firebase user. Full tenant isolation and distributed review concurrency are not claimed. Capture/revision preconditions prevent stale review only within this Local Agent session.
- Automatic multi-delivery field splitting inside one text, PDF generation, reports and accounting remain later milestones. Human association review does not make a document/date/quantity VERIFIED.

## User scope waiver before M3
User instructed to pass over manual selection/review. M2 is accepted for candidate generation and cloud persistence; unresolved associations remain unverified, no score automatically promotes them. User screenshot showed 15 proposals/35 image candidates at reviewVersion 0. This supersedes the earlier pending-manual-review gate; original procedure remains historical. M3 was explicitly authorized afterward.
