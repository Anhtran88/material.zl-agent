
2026-10-11 Play/Pause extension: 112 tests passed, including the pinned real 9Router server. New coverage: change-only saves, edited text, order-only changes, single-worker Play/Pause, fail-stop behavior, connection expiry, actual Chromium conversation-scroller isolation, missing-scroller pause, bounded catch-up and missing-anchor stop. Actual Windows/Zalo auto-scroll remains pending live acceptance.

2026-10-11 visual dashboard: 113 tests passed with the pinned real 9Router server. Added confirmed-capture counts, unchanged-poll counters and timing checks, plus actual Chromium assertions that connectivity probes do not count as Zalo data and complete saved text is rendered safely as text. Dashboard live observations on the user's Windows remain pending.

2026-10-11 automatic setup: coverage added for MCP configuration merge/backup/idempotency, preservation of invalid or conflicting settings, unsupported clients/platforms, owned 9Router key repair, catalog-only model selection, missing-provider login requirement, custom gateway preservation and local-origin access enforcement. No AI completion or Zalo-data submission is performed by setup.

Final automatic-setup validation: 120 tests passed with the pinned real 9Router server. Windows client-file behavior exercised in temporary Windows-shaped directories; actual user-machine provider login/client activation remains to be confirmed.

2026-10-11 stopped-monitor diagnosis: 122 tests passed with the pinned real 9Router server. Added actual Chromium nested-scroller selection and monitor error-code/failed-stage assertions. Generic source/scroll/cloud errors now have distinct safe diagnoses; the observed user's failure cause remains unconfirmed until the updated diagnostic is run.
