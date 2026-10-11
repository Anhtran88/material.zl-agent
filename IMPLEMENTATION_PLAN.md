# Implementation plan

Design documents were written before implementation. M1 read PoC is accepted under the user-approved reduced scope below. Later business engines remain unimplemented.

| Milestone | Deliverable | Acceptance gate |
|---|---|---|
| 1 Zalo PoC | Manual login, one exact allowed group, rendered message text/image metadata, local read-only controls | ACCEPTED — reduced scope per user instruction 2026-10-11; historical completeness, sender/message-time completeness and original download/hash waived as blockers; known limits retained |
| 2 Bundle | Bidirectional candidates, scored evidence, review | Labeled sequences and competing deliveries match; uncertain cases never auto-merge |
| 3 Cloud persistence/recovery | Firebase Auth + Firestore ingestion, Storage, cloud jobs, five identity layers, cursors | Emulator security tests and deployed ingestion/listeners; multi-device leases/fencing, replay/ACK loss/network loss; no local business persistence or duplicate accounting |
| 4 Extraction | PDF/image/Word/Excel providers, evidence | Field-level accuracy fixture and missing/ambiguous values preserved |
| 5 Validation | Date, role, quantity/unit and business duplicates | All conflict fixtures blocked and Decimal deltas correct |
| 6 PDF | Context cover, attachments, names/archive | PDF readable, expected pages, original bytes retained, collision safe |
| 7 Reports | Verified delivery revisions, lines, exports | Totals reconcile; evidence and PDF hyperlinks open; no partial commit |
| 8 Dashboard | Local monitoring/review/config | Role/privacy checks, source navigation and operational flows pass |
| 9 Hardening | Windows packaging, outages and recovery | Full XXVIII criteria, Windows restart/OneDrive/AI outages and recovery pass |

## M1 execution
1. Review architecture/schema/state machine and risk assumptions.
2. Implement narrow adapter contract with centralized user-verified selectors, exact configured conversation ID/title and one-source restriction.
3. Open persistent headed browser; allow manual login. Any uncertain/security state stops agent.
4. Snapshot the visible timeline without claiming complete history; require IDs, sender/time and known attachment classification. M1 does not automatically process every attachment.
5. Download only the operator-selected attachment candidate, using its message context; record SHA-256 and bytes in local cache. This is a supervised PoC exception, not an implemented Bundle Engine.
6. Run automated tests and record live acceptance separately. Selector contract is intentionally unpopulated until inspected on actual Zalo.
7. Push design and M1 to official repository when access is available. Do not substitute a different repository.

## Current gates — revised by user instruction 2026-10-11
M1 is ACCEPTED for the reduced read PoC based on user-observed Windows login, uploaded live captures from the configured source and the preceding 63/63 automated test run. This is a scope acceptance, not proof of complete extraction or all original Master Prompt criteria. Earlier NOT ACCEPTED entries in the report are historical and superseded for these explicitly waived gates.

The user explicitly waived historical completeness, sender/message-time completeness and original attachment download/hash as M1 blockers. Relevant business inputs are message content and the confirmation calendar date (day/month/year only) on the delivery slip. Preserve a slip's confirmation field separately from other document dates, chat-stated dates and message time. Ignore any printed clock time for this business field. Store a validated date as YYYY-MM-DD and display DD/MM/YYYY; preserve the source date string and evidence separately. Missing, unreadable or conflicting values require review; do not substitute the message timestamp. Document extraction is not implemented or proven by DOM structure reports and remains M4 work.

Source allowlisting, read-only operations, manual security handling, provenance and uncertainty remain required. No business checkpoint or accounting entry has been advanced. No assertion of complete history, original byte integrity, source-ID stability or a live network audit is made. Original-file integrity requirements for later archive/publication stages are unchanged by this M1 waiver. M2 can proceed under this revised scope; this acceptance update itself does not implement M2.

Steps 4–5 above describe the original plan: mandatory sender/time and selected original download are superseded as M1 gates by this revision. Future Bundle Engine must tolerate absent sender/time and avoid treating DOM adjacency alone as a delivery relationship.

User-requested connection extension: Local Agent loopback UI/API + local MCP adapter + pinned Windows 9Router bootstrap. Scope is browser/AI connectivity only. Completion/extraction, automatic source grouping, reporting and accounting remain gated. See docs/LOCAL_AGENT.md for operator/provider approvals, setup and integration limitations. Existing cloud chat is not automatically connected by installing this extension.

## Clarified business inputs — user instruction 2026-10-11
Preserve the full original message body, including all stated dates, materials/specifications, projects/locations, quantities, units, slip references and notes. Structured extraction supplements the original text rather than replacing it with a summary. Support multiple materials, quantities and projects in one message; retain each quantity with its unit and source span. Unclear mappings and missing fields remain unknown/reviewable; never silently collapse multiple entries into one delivery.

The delivery-slip confirmation field is date-only: day/month/year, with no time component. It is distinct from the message-stated date and from the slip issue/delivery dates. Missing or conflicting confirmation dates require review without using the chat date as a substitute. M2 preserves complete source text for grouping; M4 performs field/document extraction; M5 validates their relationships. Current read capture has a 20,000-character per-message safety bound and a truncation flag: a truncated message is incomplete and must not be presented as a complete extraction.

## Cloud-only storage revision — 2026-10-11
User requested all business data in cloud storage for realtime multi-device apps; no Firebase project currently exists. Choose Cloud Firestore + Firebase Storage, replacing SQLite/OneDrive design. See schemas/firestore.md and firebase/. Add cloud foundation before durable M2 bundle processing: authenticated ingestion, tenant/device membership, immutable capture chunks/manifests, Storage streaming, idempotency and leases/fencing. Test Firestore/Storage rules with emulators, then test real project ingestion and two-device listeners before declaring cloud ready.

Current Local Agent no longer auto-writes capture JSON or operation logs and its report-download button is disabled. It remains a memory-only preview pending cloud connection; this is not a completed storage migration or successful cloud save. Old persisted files are retained pending an explicit migration/deletion policy. Legacy file-export launchers are disabled; browser/session/runtime credential storage remains local operational state, separate from business data. Backend/cloud setup does not authorize sending Zalo evidence to AI providers. Firebase project creation, immutable database region, Auth providers and any required billing setup must be completed with the user's Google account; no cloud provision or charges have been initiated here.
