# Implementation plan

Design documents are written before implementation. Scope now: M1 only; no AI, dashboard or accounting engine.

| Milestone | Deliverable | Acceptance gate |
|---|---|---|
| 1 Zalo PoC | Manual login, one exact allowed group, bounded timeline, attachment metadata, one selected download, structured logs | Real Zalo dataset counts match; identity checked; forbidden interactions absent; valid attachment/hash; security/logout/UI drift stop; automated tests pass |
| 2 Bundle | Bidirectional candidates, scored evidence, review | Labeled sequences and competing deliveries match; uncertain cases never auto-merge |
| 3 Recovery | Persistent jobs/cache, five identity layers, cursors | Replay/crash/download interruption; no duplicate accounting or cursor gaps |
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

## Current gates
Repository access restored on 2026-10-11; initial remote main history preserved. Live Zalo login unavailable and chat.zalo.me not on current environment allowlist. Therefore M1 cannot be marked accepted from simulated tests. Milestone 2 must not start. No business checkpoint is advanced by PoC.

Offline M1 validation: 17/17 contract/schema tests passed (2026-10-11). See docs/MILESTONE_1_REPORT.md. Search/scroll and actual selector mapping remain live integration work, so gate is NOT ACCEPTED.

User-requested connection extension: Local Agent loopback UI/API + local MCP adapter + pinned Windows 9Router bootstrap. Scope is browser/AI connectivity only. Completion/extraction, automatic source grouping, reporting and accounting remain gated. See docs/LOCAL_AGENT.md for operator/provider approvals, setup and integration limitations. Existing cloud chat is not automatically connected by installing this extension.
