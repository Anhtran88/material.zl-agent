# Milestone 4 — extraction implementation, text phase

The user confirmed the multi-group Play flow works on Windows. M4 now extracts structured fields automatically before each new read_visible cloud save. No AI provider requests or local business files are introduced.

Implemented: full original text, every slash-separated full-year date (calendar validated), recognized materials including stone specifications, project labels, all supported quantity/unit observations. Every field retains exact source text and character span. Decimal values are strings, Vietnamese comma decimals and dotted thousands are supported; ambiguous dotted decimals remain unknown. Multiple dates remain separate with review required. No quantities are totaled, attributed across multiple projects, or financially activated.

The shared dashboard displays these observations together for all groups. Read captures persist extraction in canonical reportJson using the existing durable job/checkpoint transaction. Cloud-restored earlier captures can be parsed in memory for display; they are not rewritten or claimed to contain a persisted extraction revision. New captures persist ruleset m4-text-v1. No-change polling still performs no write.

Remaining M4 scope: controlled image byte acquisition and OCR, original document providers PDF/Word/Excel, confirmation-date evidence on the slip and real-world accuracy acceptance. Current image metadata cannot substantiate a slip date. slipConfirmationDate stays null / NOT_READ; message dates are never substituted. M4 is NOT fully accepted, and M5 does not start.

Validation: seven focused tests cover actual example quantities, exact evidence spans, invalid dates, decimal ambiguity, ordinary chatter, multiple projects/dates, revision identity, and Firestore REST/CAS fault-model roundtrip plus duplicate reuse. These are automated fixture checks, not live Windows/Zalo/Firestore verification.
