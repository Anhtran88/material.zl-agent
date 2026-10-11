# Firebase setup — materialzlagent

User supplied a Firebase settings screenshot on 2026-10-11 confirming project name MaterialZlAgent, project ID materialzlagent and project number 939657441007. The CLI target is recorded in firebase/.firebaserc. This session has no authenticated Firebase/Google Cloud provisioning connection. Firestore creation/location, Auth configuration, bucket and billing remain unverified. No cloud resources, rules, billing or actual storage writes have been deployed. The committed `firebase/` folder is a deployment scaffold, not a connected application. Client rules deliberately deny all access; Admin SDK/backend security requires separate authorization tests.

## Concrete initial setup

1. Existing project: **MaterialZlAgent**, ID **materialzlagent**. Open https://console.firebase.google.com/project/materialzlagent/overview and verify you are configuring this project. Do not create a second project.
2. Create **Cloud Firestore Standard, Native mode**, production/locked rules. Suggested region for Vietnam: **asia-southeast1 (Singapore)**, subject to the console's supported choices. Database location is an enduring decision; check before creation. Do not choose public/test rules.
3. Enable Firebase Authentication email/password initially, create the owner user and record its UID. No password, service-account JSON or private key goes into chat or Git.
4. Configure private Firebase Storage in a suitable colocated region. Storage/backend hosting may require **Blaze billing**; review current console pricing before linking billing. Budget alerts notify, they do not cap spending. Defer Storage activation if billing has not been approved; text-only Firestore development can proceed separately.
5. Provide Project ID, selected Firestore location, Storage bucket name (when created), and owner UID. These are identifiers, not login credentials. Authenticated deployment access must be configured separately; do not send key files into chat. Never put an Admin credential in Local Agent/mobile/frontend.

## Implementation/deployment gate

- Implement authenticated HTTPS ingestion (Firebase ID token), tenant membership and registered device/source validation server-side. Reject arbitrary tenant IDs/source IDs, constrain payload/size and use idempotency manifests.
- Configure backend workload identity/scoped IAM, not shared service-account JSON on devices. Secrets stay in managed cloud secrets or local operational credential stores, distinct from business data.
- Implement tenant read rules + authorized Storage access, validate with Firebase emulators for unauthenticated/cross-tenant/revoked/privilege-escalation cases. Bootstrap deny-all scaffold is not the final app permission model.
- Use deployment tooling from inside firebase/ with an explicitly reviewed target project; no default/guessed production project. Create the required indexes. Deploy only after backend/rules tests pass; do not use test-mode rules to bypass missing setup.
- Validate a real capture commit, same-ID retry, crash/ACK loss, two concurrent devices, stale fencing rejection, listener updates, date-only values and network outages. Only then expose “saved to cloud” status.

## Local transition behavior

Updated Local Agent stops auto-saving `cache/*/capture.json` and `logs/bridge.jsonl`; bounded metadata and preview data remain in memory, the JSON report-download button is disabled. Old files remain untouched to avoid unintended evidence deletion. Legacy file-export CLI launchers are disabled. Current operation is preview only and is not durable cloud ingestion. No business cursor/accounting commit occurs. Updating Windows source and restarting is required for these changes to affect the user's running agent.

The Zalo browser profile can contain managed website caches and is itself a credential; it and Local Agent/9Router operational credentials remain local. This implementation does not claim an OS/browser-wide ban on disk writes. Future memory-only business handling and disabled Firestore offline persistence do not replicate a Zalo login to other devices. Those devices read authorized Firestore data; a registered Windows Agent reads its own local Zalo session.

## User-requested unrestricted Firestore rules — 2026-10-11
User requested rules without restrictions after showing Firestore default test-mode expiry. firebase/firestore.rules now grants public read/write with no expiry. This explicitly supersedes earlier deny-all Firestore scaffold instructions; Storage rules remain deny-all. Unauthenticated clients can read, create, change and delete all Firestore documents, including tenant membership and business records. This rule does not provide tenant isolation or production authorization and does not make cloud ingestion implemented. No deployment was performed from this session; paste the rule in Firebase Console and Publish to apply. Restore tested authorization rules before relying on Firestore client data for membership/accounting decisions.

## Public-rule RAW capture connection — 2026-10-11
User supplied Firebase Web configuration for materialzlagent, including the public client API key and Storage bucket identifier materialzlagent.firebasestorage.app. Added a fixed-project REST capture store for the explicitly requested public Firestore rules. It is an interim RAW prototype, not the authenticated tenant/device backend described above. Firebase client API keys identify a project; public rules still allow unauthenticated access. A declared Storage bucket name does not establish Storage activation or billing.

After Windows source update/restart, each read/structure operation writes one bounded cloud capture to tenants/default/captures/{UUID}. Fields include reportJson (full original report as JSON string), payloadSha256 (capture JSON identity, not an original-image hash), operation, sessionId, schemaVersion, RAW layer and server receivedAt. receivedAt is capture receipt time, not a slip confirmation date. No browser credentials/URLs are captured. No local capture/log files or offline disk fallback. The API returns cloudStorage.saved=true with documentPath/commitTime only on verified cloud commit or readback after lost ACK. Network/permission failure revokes reads; oversized captures over 700,000 UTF-8 bytes stop pending future chunked ingestion. Retry within one operation uses the same UUID and create-only precondition; recapturing in a new operation creates another RAW capture, not deduplicated business/accounting records.

The UI report-download button stays disabled because data is cloud-only; results remain visible in RAM. Navigate Firebase Data → tenants → default → captures to see committed captures. Structured message/delivery projections, Auth, tenant isolation, realtime frontend listeners, image/PDF Storage upload and complete multi-device fencing are not implemented by this prototype.

Validation: 67/67 automated tests passed (mock Firestore transport plus real Chromium/MCP/9Router checks). Actual executor connection to firestore.googleapis.com is blocked by the inherited proxy (403 Forbidden); the setup connectivity-test write did not return a verified receipt. No real cloud save is claimed. Verify from the user's Windows Agent before cloud acceptance.
