# Zalo Material Delivery Manager

Read ARCHITECTURE.md and IMPLEMENTATION_PLAN.md first.

**Current storage direction:** Firestore + Firebase Storage for business data. Current Local Agent stores bounded RAW read/structure reports directly in materialzlagent Firestore under tenants/default/captures using the user-requested public-rule prototype. No automatic local capture/log persistence or report download. Real Windows/cloud verification is pending; this environment's proxy blocks Firestore. Authenticated ingestion, multi-device business processing and Storage uploads remain unimplemented. See schemas/firestore.md and docs/FIREBASE_SETUP.md.

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

## Manual login browser on Windows

Install Python 3.12 and Git, clone this repository, then run from PowerShell:

```powershell
git clone https://github.com/Anhtran88/material.zl-agent.git
cd material.zl-agent
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-ZaloLogin.ps1
```

The script creates the project's `.venv`, installs the package and Playwright Chromium, and opens a headed manual-only login browser. It does not need Zalo selectors and does not read/search groups, join groups, download attachments or send content. Close with Enter in the terminal. Profile stays under `%LOCALAPPDATA%\ZaloMaterialAgent\browser-profile`; never sync or share it. Use a private Windows account and its user-only folder permissions. A successful login is not M1 acceptance; live adapter mapping and coverage verification are still required.

Cloud execution requires the environment owner to configure permitted Zalo destinations using the environment settings workflow and enable an interactive browser. Current agent tools expose read-only environment status, not configuration editing or browser presentation. Local Windows login does not change the cloud network policy.

## Automated local DOM inspection (replaces manual F12 screenshots)

Close the manual login browser using Enter in its PowerShell window before starting a second process on the same profile. Run `.\.venv\Scripts\python.exe -m material_agent.inspect_dom`. Open the allowed group manually, handle any login/security challenges manually, then press Enter. The helper checks the user-observed title and candidate group ID, then reads only DOM structures for rendered text/image containers with that group ID. It performs no clicks, scrolling, downloads or Zalo writes and reads no cookies, storage, image URLs, message text or application internal state. It exports `%LOCALAPPDATA%\ZaloMaterialAgent\cache\{UUID}\dom-report.json` and opens its folder. Review/share this structure-only report for adapter mapping; keep profile and source evidence local. Captured ancestor attributes are diagnostic metadata; this is not timeline/attachment acceptance or an assertion of ID stability. Changed selectors fail closed.

## Local Agent + automatic 9Router setup

Download the latest project, close the earlier Agent browser, then run `scripts\Start-LocalAgent.cmd` on 64-bit Windows. The bootstrap installs a checksum-verified portable Node runtime and locked 9Router version, protects local credentials, starts two loopback services and opens the control page. Use **Mở Zalo → Kết nối đọc nhóm → Kiểm tra DOM**. Use **Duyệt nhà cung cấp AI trong 9Router** to approve your own provider/account; no source data is sent to AI by this version. You can export the DOM report without manually using F12.

See [Local Agent guide](docs/LOCAL_AGENT.md) for MCP client configuration, provider setup, stopping, security controls and validation limits. A compatible local MCP client can use the bridge; the current cloud chat is not connected to your desktop automatically.

## Milestone 2 — candidate bundle review
After updating/restarting the Windows Agent, read the allowed rendered timeline. “Delivery Bundle — Milestone 2” displays original messages and scored image-to-message alternatives. Select individual image links, optionally merge follow-up messages, enter a reason and save to Firestore. Captures and bundleRevisions are created atomically; originals/previous review snapshots remain. No automatic uncertain merge, confirmed date extraction or accounting/checkpoint occurs. Live M2 acceptance is pending. See docs/MILESTONE_2_REPORT.md for the ground-truth checklist and limitations.
