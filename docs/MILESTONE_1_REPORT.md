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
