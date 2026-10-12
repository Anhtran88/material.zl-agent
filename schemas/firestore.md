# Cloud Firestore schema — authoritative design

Supersedes schema.sql (historical relational reference only). All business records are tenant-scoped under `tenants/{tenantId}`. IDs and references cannot cross a tenant. Server validates ownership, allowed source, payload schema/size and state transitions; Firestore has no foreign-key or unique constraints. Authentication is Firebase Auth, not a shared service-account key on Windows. Backend uses scoped IAM/workload identity; Admin SDK bypasses client rules and must enforce tenant authorization itself.

| Collection under tenant | Main fields / identity |
|---|---|
| members | document ID = Firebase UID; role = owner/reviewer/viewer; provisioning backend only |
| agents | registered device identity, assigned sources, heartbeat, status; no browser sessions or provider secrets |
| sources | Zalo account reference, owner; no credentials |
| conversations | sourceId, externalId, exact title, allowed, version |
| captures | captureId/idempotency key, agentId, conversationId, manifest, chunk status, receivedAt, committedAt |
| messages | conversationId, captureId, externalId nullable, candidate DOM IDs, fingerprint/version, full rawText, rawMetadata, capturedAt, sender nullable, messageTimestamp nullable |
| attachments | message/capture association, externalIdentity nullable, kind, originalName, fileId nullable, state |
| files | content hash when bytes exist, bucket/object path, immutable object generation, sizeBytes, mediaType, retentionState; no public download token or signed URL |
| bundles | conversationId, createdAt, activeRevisionId nullable, activeDeliveryId nullable, version |
| bundleRevisions | bundleId, revision, fingerprint, confidence, rulesetVersion, state; immutable evidence membership in separate collections |
| bundleMessages / bundleAttachments | revisionId, evidenceId, reason; deterministic pair document ID |
| documents / documentPages | attachmentId, fileId, role, dates/date originals; page number, textContent, evidence locations |
| extractions / extractionEvidence | revisionId, fieldName, original/normalized values, unit, confidence, method, layer; exactly one message span or document page/location |
| materials / projects / suppliers | tenant-scoped dictionaries, names/codes, normalization version |
| deliveries | bundleId, revisionId, projectId, supplierId, confirmedDeliveryDate (YYYY-MM-DD, date-only), confirmation original/evidence, chatStatedDate separately, documentNumber, validationStatus, accountingActive, pdfFileId |
| deliveryLines | deliveryId, materialId, specification, unit; decimal strings for requested/ordered/delivered/received/accepted/returned quantities, weight, evidence refs |
| validationIssues / reviewAudit | conflicts, evidenceIds, resolution actor/server timestamps, immutable audit events |
| checkpoints | document ID = conversationId; scannedCursor, finalizedCursor, version, lastCaptureId; no assertion of complete history without verified cursor |
| processedMessages / processedAttachments / processedBundles | tenant-scoped deterministic identity, committed revision and terminal reason |
| runs / jobs / agentLogs / aiRequestLogs | state, attempts, nextRetryAt, ownerAgentId, leaseExpiresAt, fencingToken, version; safe metadata only |
| publicationOutbox | revisionId, fileId, immutable Storage path/generation, state, idempotency key |
| identityReservations | hashed tenant+source+external ID or strong identity key; target ID, rulesetVersion; transaction create, never weak fingerprint as automatic discard |

Full message text is retained separately from extracted dates/material/project/quantity/unit; multiple entries keep separate source spans. Bounded capture truncation stays explicit, never silently accepted as complete. Oversize message/page text moves into private Storage as UTF-8 with reference, byte count and integrity metadata; do not truncate to fit Firestore's 1 MiB document limit. Documents contain bounded metadata, not binary/base64 images or unbounded growing arrays. Membership/evidence/line records are separate documents; page chunks and manifests support large uploads without one giant transaction.

Decimal strings are calculated server-side with Decimal, not JS floating point or an LLM. Server timestamps are capture/audit times only; they cannot supply the slip confirmation date. Date-only confirmation is distinct from slip issue date, chat-stated date and message timestamp.

# Concurrency and deduplication

Five layers remain: source message identity, attachment identity, binary identity when available, immutable bundle revision identity, reviewable business duplicate candidates. Hash/identity reservations are tenant-scoped, avoid cross-tenant existence leaks. Unstable IDs or missing sender/time produce candidates requiring review, never irreversible discard.

A backend transaction claims one job with version comparison, server-clock lease expiry and incremented fencing token. Every subsequent write validates token+owner+unexpired lease. A stale agent cannot commit after another agent takes over. Clients never choose their own tenant or promote accounting state. Each bundle's activeDeliveryId pointer is changed transactionally with the revision; this replaces SQLite's partial unique index. Reports query the active pointer/current projection, not arbitrary client-written accountingActive flags.

# Ingestion, checkpoints and Storage saga

Capture arrives over authenticated HTTPS to an ingestion backend using a stable captureId and bounded chunk sequence. Validate source allowlist server-side; store chunks idempotently, then commit manifest only after all expected chunks exist. ACK includes durable capture identity, not merely successful local DOM read. Lost ACK causes retry of the same captureId. scannedCursor changes only after durable manifest completion. finalizedCursor changes only after safely terminal contiguous processing; unverified history cannot invent a cursor. Backend sends realtime listener updates after cloud commit.

Storage upload uses an immutable tenant/job/object key and generation preconditions. Verify content metadata and expected bytes when actual bytes are processed; never pretend blob DOM metadata is an original file. PREPARED/outbox transaction does not activate accounting. Verify uploaded object generation and publication artifacts, then transactionally activate the revision and advance eligible checkpoint. Firestore+Storage is a saga, not one atomic transaction. Recovery checks existing generations/manifests; no blind overwrite or duplicate accounting. Expired orphan staging objects are cleaned server-side only after lease/reference checks. Backups/PITR and lifecycle/retention are cloud policies, not SQLite/OneDrive copies.

# Realtime clients and persistence

Web/mobile clients use Firebase Auth and tenant-scoped, bounded Firestore listeners with pagination and unsubscribe. Backend performs all business writes; owner/reviewer actions use validated endpoints with revision preconditions. Client rules stay deny-all until member read rules are tested in the Firebase Emulator Suite for cross-tenant denial, revoked users and unauthenticated requests. Storage reads use authorized backend streaming or short-lived in-memory access; no public links in business records.

No local SQLite, capture JSON, offline outbox or business log persistence. Firestore client persistent offline caching is disabled (memory-only). Network loss pauses durable ingestion; keep only bounded pending data in RAM, no successful commit/checkpoint claim. Closing the agent loses unacknowledged RAM data, requiring operator recapture; history completeness was waived but data loss must stay explicit. OS/browser managed caches, swap and downloaded program files are not eliminated by this application policy. Zalo credential profile, local bridge credentials and 9Router runtime/config remain device-local operational dependencies; never replicate them to Firestore. Strict zero browser disk writes would require an ephemeral Zalo browser and manual login on every restart, which is a separate operating-mode change.

# Current M2 persistence mapping
The implemented prototype stores complete capture/Engine JSON in captures.reportJson, queryable provisional bundle revision metadata plus proposalJson under bundleRevisions, and parentCapturePath inside the reviewed capture. Each snapshot/review is create-only; source RAW evidence, link alternatives and review reason/version are retained through the immutable capture chain. Bundle identity is provisional from the source+message DOM container. No normalized business collection projection or active revision pointer is implemented yet. This capture-scoped representation does not replace future tenant/backend validation, cross-capture deduplication or distributed jobs/fencing.

# Current M3 persistence mapping
captures use read_visible_<canonical payload SHA-256> / bundle_review_<SHA-256> for new M3 operations. jobs share the target capture ID and retain PREPARED reportJson, nextArtifact, attempts/lastAttemptAt, leaseToken and COMPLETED state. sourceLeases and checkpoints use the SHA-256 of the configured source ID. evidenceArtifacts are immutable-observation-version signatures (kind/source/DOM identity/content/metadata); repeated upserts write the same fields without claiming stable source identity. Final capture + bundleRevisions + checkpoint + job completion + lease release share one CAS commit; staged artifacts do not advance checkpoints. Checkpoint lastDurableCapturePath/captureSequence supports rendered-snapshot resume; scannedCursor/finalizedCursor are not inferred. Older UUID captures remain untouched. Binary/business identity registries and authenticated backend are not implemented in this mapping.

### M4 text observations
New captures.reportJson contains extraction {schemaVersion:1, rulesetVersion:m4-text-v1, rows:[...]}. Each row has extractionId (hash of ruleset/source/container/original text), originalText, messageDates/materials/projects/quantities observations with value/raw/span/basis. Decimal values are strings; invalid/ambiguous observations retain raw text with null values. Source DOM identities remain provisional. slipConfirmationDate:null, slipDateStatus:NOT_READ, accountingActive:false. This is durable with the containing capture and checkpoint, not a separately finalized accounting collection. Cloud-restored legacy snapshots are parsed for display only and remain immutable.

### Local OCR observations (M4)
New reportJson adds imageExtraction.rulesetVersion=m4-local-ocr-v1. attachments[].images[].ocr stores status, provider, lines{text,confidence,box}, confirmationDateCandidates{value ISO date,displayDate DD/MM/YYYY,labelLine,dateLine,rawLabel,rawDateLine,confidence,status,basis}, observedImageSha256 and byteLength. No image binary or media URL is persisted by this phase; the hash identifies observed blob bytes only, originalBytesVerified=false. The RAW capture and observedJson artifact can contain OCR text as evidence; source identities and date-to-message relationships remain provisional. extraction.rows[].slipDateCandidates carries source image/container/hash and associationScore/status; slipConfirmationDate stays null. Existing immutable captures are retained, version upgrades create new snapshots through the same recoverable commit path.

### Image review rendition and concise slip fields (M4 v2)
imagePreviews/{sha}: sourceId/domContainerId/domImageId, JPEG base64 <=180000 decoded bytes, sha, dimensions, originalBytesVerified:false, receivedAt. imagePreviewLinks/{source/container/image identity hash}: CAS-updated binding and previewJson. Immutable rendition IDs include source/image identity and rendition hash; the bounded preview and pointer are committed atomically. Lost ACK is checked by reading both. Index exemptions for jpegBase64 and previewJson are added to the index scaffold (not deployed from this environment). Preview commits precede the referring capture; a failed capture can leave an unreferenced cloud preview/pointer, never an advanced checkpoint. No local image copy is created.

New imageExtraction.rulesetVersion=m4-slip-fields-preview-v2 and images[].preview reference these renditions. images[].ocr.fields holds documentDates, materials, requestedQuantity, receivedQuantity, project, recipient, candidate status/confidence and selected evidence line indices. Document date role remains unverified; confirmation-date candidates remain separate. fullPageTextStored:false; only selected essential-field/date evidence lines are persisted. originalLineIndex/lineIndexBasis preserve compacted and legacy evidence references. Unchanged DOM comparison excludes derived OCR/preview metadata, so viewing or adding previews does not itself create repeated read captures. Review-only preview retrieval does not update the historical/business checkpoint.
