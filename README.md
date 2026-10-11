# Zalo Material Delivery Manager

Read ARCHITECTURE.md and IMPLEMENTATION_PLAN.md first. M1 is a supervised, fail-closed PoC; live acceptance is pending. No bundle/accounting/AI/dashboard implementation yet.

Windows Python 3.12+:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
playwright install chromium
Copy-Item config/selectors.example.json config/local.json
# Inspect Zalo DOM manually and configure exact allowed ID/title and selectors.
zalo-poc --config config/local.json
# Download one selected attachment after reviewing captured context:
zalo-poc --config config/local.json --message VERIFIED_MESSAGE_ID --attachment VERIFIED_ATTACHMENT_ID
```

The selector contract requires data-conversation-id/data-title on source and active source, data-message-id on messages, data-attachment-id/data-kind on attachments and data-action=download on download controls. These are an explicit contract, NOT verified attributes of live Zalo. Adapt centralized extraction to actual DOM before live acceptance; do not inject guessed IDs or relax identity checks. Ready/security selectors must distinguish actual login and verification states. No screen coordinate fallback.

Only visible messages are captured; no claim of historical completeness. Source must already be visible in the conversation list; automated search and scrolling await verified live DOM. Login is manual. Challenges/UI drift stop automation. Navigation may mark messages read; evaluate this platform effect during acceptance. Never enter the composer. Browser profile/raw timeline contain private data: keep local Windows user-only permissions, outside OneDrive and Git. No automatic cache deletion or business checkpoint in M1.

Run offline checks: `PYTHONPATH=src python -m unittest discover -s tests -v`.
