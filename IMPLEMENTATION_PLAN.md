# Implementation plan

Design documents were written before implementation. M1 read PoC is accepted under the user-approved reduced scope below. Later business engines remain unimplemented.

| Milestone | Deliverable | Acceptance gate |
|---|---|---|
| 1 Zalo PoC | Manual login, one exact allowed group, rendered message text/image metadata, local read-only controls | ACCEPTED — reduced scope per user instruction 2026-10-11; historical completeness, sender/message-time completeness and original download/hash waived as blockers; known limits retained |
| 2 Bundle | Implemented capture-scoped bidirectional candidates, scored evidence, local review/merge/split, Firestore revisions | 87/87 tests pass; labeled Windows live comparison and reviewed revision persistence pending; no M3 yet |
| 3 Cloud deduplication/recovery | Implemented exact snapshot replay, observation versions, durable jobs, CAS leases, cloud checkpoint/resume | 103 tests pass; Windows M3 live acceptance pending. Binary/business identity and authenticated cloud foundation require later evidence/setup |
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

## Firebase project identified — 2026-10-11
User screenshot confirms MaterialZlAgent (materialzlagent, project number 939657441007). firebase/.firebaserc now selects this project. This supersedes earlier no-project setup status, but does not establish Firestore/location, Auth, Storage, authenticated deployment or actual cloud ingestion. Cloud acceptance gates remain pending.

## Firestore rule override — 2026-10-11
User explicitly requested unrestricted, non-expiring Firestore rules. Committed allow read/write if true, including unauthenticated clients; no deployment performed. This supersedes the earlier deny-all Firestore scaffold for the current requested configuration. Tenant isolation/security acceptance gates remain unmet; unrestricted access is not proof of cloud readiness. Storage policy was not changed.

## RAW Firestore connection implementation — 2026-10-11
Added fixed-project REST RAW capture commits for materialzlagent using the user's public Firebase client config and requested public rules. One bounded immutable capture per read/structure operation, server receipt time, create-only retry/readback, no local fallback, explicit verified cloud receipt. This replaces memory-preview-only behavior on updated Windows installs. 67/67 automated tests passed; actual environment Firestore probe blocked by proxy 403, so real cloud save pending Windows verification. Authenticated ingestion, chunking, tenant isolation, multi-device state leases and Storage uploads remain gated cloud-foundation work; this interim prototype is not the full schema/services implementation.

## Cloud write observation — 2026-10-11
User Firebase Console screenshot shows three documents in captures and user confirms save works. RAW cloud writes have user-observed live evidence; content/receipt matching remains uninspected. Visible cloud status and local-only no-Zalo connectivity-test write added, with safe error diagnostics; 70/70 automated tests pass. Full authenticated cloud foundation and M2 business processing remain unimplemented.

## M2 implementation — 2026-10-11
Implemented conservative DOM-order candidates in both directions, per-image review, follow-up message merge/split, version/reason audit and atomic capture/bundleRevisions Firestore writes. Full source text remains intact, dates/quantities are not promoted to verified fields. 87/87 automated tests passed. See docs/MILESTONE_2_REPORT.md for evidence, limitations and live acceptance procedure. M2 live acceptance is pending; M3 must not start yet.

## M2 waiver and M3 implementation — 2026-10-11
User waived manual per-image review and accepted M2's proposal-generation scope, then authorized M3. Implemented RecoverableFirestoreStore, canonical snapshot reuse across sessions, versioned observation artifacts, bounded cloud PREPARED jobs/chunks/attempts, server-read-time CAS leases/fencing and atomic final capture/checkpoint commit. Added cloud-only UI resume without opening Zalo. 103/103 tests passed. Binary/business identities remain explicitly waiting for verified bytes/extracted fields; no historical/final checkpoint is invented or accounting activated. Older UUID captures are retained without migration. See docs/MILESTONE_3_REPORT.md. M3 live acceptance remains pending; M4 is not started.

2026-10-11: M3 extended with Play/Pause backend monitoring, verified conversation bottom scrolling, Firestore resume and change-only saves. Bounded catch-up to the saved DOM anchor is implemented; live scroll acceptance remains open; no M4 advancement.

Multi-group update: checkboxes for both user-named groups, cloud-persisted added groups/selection, exact-name browser selection and candidate ID binding, separate source recovery/checkpoints and a shared snapshot summary. M4 extraction/financial acceptance and full historical cloud summary queries remain outside this change.

## Current step — M4 text phase
User confirmed multi-group Play success. M4 begins with evidence-backed message extraction and a shared structured table, cloud-only persisted alongside new captures. See docs/MILESTONE_4_REPORT.md. The slip date remains unknown until OCR/document evidence exists; image OCR and PDF/Word/Excel providers remain within the M4 gate. Do not start M5 or mark M4 fully accepted yet.

## M4 photo OCR phase — 2026-10-12
Fixed browser blob acquisition and local in-memory OCR now enrich new captures automatically; dates have explicit-label evidence and remain candidates until association/date validation. Shared dashboard exposes OCR counts and proposed dates. Software dependencies install via Start-LocalAgent.ps1. No provider data transmission or local image/report files. Actual Windows receipt accuracy and PDF/Word/Excel integration remain within M4 acceptance; M5 remains blocked by that gate. See docs/MILESTONE_4_REPORT.md for precise limits.
