# UUID Identifiers and Opaque Object Keys Design

**Date:** 2026-08-01

## Goal

Replace the integer primary keys on `documents`, `jobs`, and `artifacts` with UUIDs, and rebuild both object-key formats around those UUIDs so that no user-supplied text ever reaches a storage address.

The work is driven by a concrete defect rather than a stylistic preference. `POST /documents` must write a `NOT NULL` `object_key` at `INSERT` time, but `documents.id` is assigned by Postgres *during* that insert — so the key cannot be built from the document's own ID. The current code works around this by interpolating a throwaway `uuid4()` into the key (`api/routes/documents.py:34`). That value is never stored as a column, never queried, and referenced by nothing: it is a uniqueness nonce masquerading as an identifier, and it means every document effectively carries two IDs, one of which is meaningless. Application-generated UUIDs remove the ordering constraint that created it.

The same defect appears on the output side. `worker/services/processing_service.py:65` builds artifact keys as `artifacts/{job_id}/{stem}.md`, where `job_id` is likewise standing in for uniqueness rather than describing anything anyone would ask for by name, and where `account_id` is missing entirely — so artifacts, unlike raw uploads, are not tenant-partitioned and cannot be scoped by IAM policy or S3 lifecycle rule per account.

Both key schemes also embed `file_name`, an unvalidated client-supplied string. Because the API never receives the uploaded bytes, `file_name` is an assertion the server cannot verify. Embedding it produces signature mismatches on presigned URLs when it contains characters requiring URL encoding (the `403 SignatureDoesNotMatch` observed during manual testing), duplicates a value already held in `documents.file_name`, and — since S3 keys are immutable — guarantees the key becomes stale the moment a document is renamed.

In scope:

- `documents.id`, `jobs.id`, `artifacts.id` become `UUID`, generated application-side with `uuid.uuid4()`.
- `jobs.document_id`, `artifacts.document_id`, `artifacts.job_id` follow as `UUID` foreign keys.
- The RabbitMQ message payload's `job_id` becomes a string, and the consumer parses it as a UUID.
- `documents.file_name` is dropped: the column, the `CreateDocumentRequest` field, and the `DocumentResponse` field. `POST /documents` takes no request body.
- Raw key becomes `raw/{account_id}/{document_id}.pdf`.
- Artifact key becomes `artifacts/{account_id}/{document_id}.md`.
- `artifacts` drops `unique(object_key)` and gains `unique(document_id, artifact_type)`; `ArtifactRepository.create` becomes an upsert on that constraint.
- The `one_active_job_per_document` partial index is dropped and recreated around the `document_id` type change.
- Raw key construction and document UUID generation move from `api/routes/documents.py` into `DocumentService`.
- Three Alembic migrations, one per phase, each explicitly destructive.
- Test updates alongside each phase, plus new coverage for key formats and upsert behaviour.

Out of scope (explicit non-goals):

- **The document lifecycle gap.** A `POST /documents` that is never followed by an upload leaves a permanent `documents` row with no status field, no cleanup, and no way to regenerate an expired presigned URL. This was investigated in detail and deliberately deferred; see Future Work.
- **`accounts.id` stays an integer.** Accounts never appear in a URL path — authentication is the `X-API-Key` header and the account is resolved from it — so there is no enumeration surface to close. It remains in object keys solely for prefix-scoping. See Design Decision 2.
- **`Content-Disposition` on download URLs.** Would have been required to preserve download filenames had `file_name` been retained; moot once it is dropped. See Design Decision 4.
- **Content-hash deduplication.** Considered and rejected on the grounds that it would defeat the project's purpose. See Design Decision 10.
- **S3 bucket versioning**, presigned-URL refresh, `DELETE /documents/{id}`, `Idempotency-Key` support, and document-level status polling. All noted in Future Work.
- **UUIDv7.** Not available in the Python 3.13 standard library. See Design Decision 1.

## Design Decisions

### 1. UUID primary keys, generated application-side with `uuid4`

Four options were weighed against the pre-insert-ID problem.

*Pre-fetch the sequence* — `SELECT nextval('documents_id_seq')` before the insert — keeps integer keys and produces the shortest keys of any option, with no schema change at all. Rejected because it is an uncommon technique used to work around a problem the conventional answer solves directly; a reader encountering it in a route handler would reasonably ask why, and the answer points straight back at UUIDs.

*Integer PK plus a separate public UUID column* (the Stripe split) keeps integer joins and foreign keys while exposing an opaque external identifier. Rejected because it reintroduces two identifiers per row, which is the specific problem this design exists to remove, and because its performance advantage is unreachable at this project's scale.

*Snowflake-style 64-bit IDs* pack a timestamp, machine ID, and counter into a bigint, giving int-sized, time-sortable, distributed-safe keys. Rejected as requiring machine-ID assignment and introducing clock-skew sensitivity for no benefit here.

*Application-generated UUIDs* were chosen. Being able to know an ID before the row exists is precisely the property the object key needs, and it is the reason UUIDs are conventional in this situation.

`uuid4` (random) is used rather than `uuid7` (time-ordered). UUIDv7 would give better B-tree insert locality — random UUIDs scatter inserts across the index, causing page splits and fragmentation where sequential keys append to a hot rightmost page — but `uuid.uuid7()` landed in Python 3.14 and this project runs 3.13, so it would mean a third-party dependency. The insert-locality cost is not reachable here: the pipeline's bottleneck is CPU-bound PDF parsing measured in seconds per document, orders of magnitude slower than any index write. This is worth restating because the project's purpose is load testing and the objection is therefore live rather than theoretical — but reaching a regime where UUIDv4 index behaviour is visible next to parsing cost would require sustained insert rates in the tens of thousands per second. Switching to UUIDv7 later is a one-line change to ID generation; the column type and everything downstream are unaffected.

### 2. UUIDs on documents, jobs, and artifacts — but not accounts

The technical driver, needing an ID before the insert, applies only to `documents`. Jobs and artifacts have no such constraint, and after this change neither appears in an object key.

They are converted anyway, for consistency: `GET /jobs/{job_id}` is a top-level route, so a sequential `jobs.id` is directly probeable and leaks total processed volume in the same way `documents.id` would have. Mixed identifier formats within one API would also force every consumer to handle two shapes. An earlier draft of this design argued jobs were "subordinate resources" reached only through a document they already own; that argument was withdrawn, because the top-level `GET /jobs/{job_id}` route contradicts it.

`accounts.id` is excluded on different grounds: it appears in no URL path, so no client ever sees or supplies it, and there is nothing to enumerate. It stays in object keys only to give each tenant a distinct prefix for IAM scoping and lifecycle rules.

### 3. No user-supplied text in object keys

`file_name` is removed from both key formats. Four distinct failure modes motivated this, in rough order of likelihood:

Presigned-URL signature mismatches. Characters requiring URL encoding — spaces, `+`, `#`, `?`, `%`, non-ASCII — can differ between how boto3 encodes when signing and how a client encodes when sending, producing `403 SignatureDoesNotMatch`. A `#` is worse, since some clients treat it as a fragment delimiter and truncate the URL. This was observed in practice during manual Postman testing.

Permanent staleness. S3 keys are immutable; there is no rename operation, only copy-and-delete. A filename embedded in a key can never be corrected after the document is renamed, leaving `documents.file_name` and the key permanently disagreeing.

Key length. S3 caps keys at 1024 bytes UTF-8. A long filename plus prefix can approach this, failing with an opaque error.

Latent path injection. A `file_name` of `../../etc/passwd` produces a key containing a literal `..`. This is *not* an S3 traversal vulnerability — S3 keys are flat, opaque strings and path segments are never resolved — but it becomes one the moment any consumer parses the key, syncs it to a filesystem, or hands it to an S3-compatible store with different normalisation. The current safety rests on a property of S3 rather than on validation.

### 4. `file_name` is dropped entirely, not merely removed from keys

Once removed from both keys, `file_name` is load-bearing for nothing. It is not identity, not part of any storage address, and never seen by the parser, the queue, or the backpressure path. Its only remaining use is a display field on `GET /documents/{id}`, on a system with no UI.

Given the project's purpose is load testing, retaining it would have required `ResponseContentDisposition` on presigned download URLs purely to stop every artifact from downloading as `markdown.md` — real work in service of an experience nobody has. It would also have required length and control-character validation on `CreateDocumentRequest.file_name` (currently a bare `str` with no constraints) before feeding it into an HTTP response header.

Dropping it removes the entire problem space — encoding, validation, header injection, display naming — rather than managing it. It also marginally simplifies load-generator scripts, which no longer need to synthesise a filename per request. Re-adding a nullable column later is a trivial migration if a UI ever appears.

### 5. `object_key` remains a stored column, not a derived value

After this change `object_key` is fully derivable from `account_id` and `id`, which makes deleting the column and computing the key on read look attractive. It is deliberately kept.

Storing the key is the single property that makes this redesign a non-migration for existing rows: every read path uses `document.object_key` verbatim, so old rows keep resolving to old keys and new rows to new keys, indefinitely and without a backfill. Had keys been derived at read time, changing the format would have instantly orphaned every stored object. The column is the durable contract; the format is an implementation detail that is now free to change again.

### 6. Artifacts overwrite; the uniqueness constraint moves to `(document_id, artifact_type)`

Generated Markdown is *derived* data — a deterministic function of the input PDF and the parser, regenerable at any time — rather than a *record* of something that happened. Derived data has one correct address holding the current best output; reprocessing after a parser fix should correct it in place.

`job_id`, which currently discriminates artifact keys, fails the test that decides whether something belongs in a key: **is this a discriminator anyone would ask for by name?** Users ask for "the 256px thumbnail" or "the v2-parser output"; nobody asks for "the Markdown from job 7". It is in the path for the same reason `uuid4()` is in the raw path — convenient uniqueness, not meaning.

This forces a constraint change. Keying by `document_id` means a second processing run computes a key identical to the first, which violates the existing `unique(object_key)` on `artifacts` and raises `IntegrityError`. Reprocessing is genuinely reachable: the `one_active_job_per_document` partial index prevents two *concurrent* jobs for a document, but a new job may be created once the previous one leaves an active status.

`unique(object_key)` is therefore **replaced** by `unique(document_id, artifact_type)` rather than supplemented. Since the key is derived from exactly those two fields, keeping both would encode one rule as two constraints, which is how constraints eventually drift apart. `ArtifactRepository.create` becomes `INSERT ... ON CONFLICT (document_id, artifact_type) DO UPDATE`, refreshing `job_id` so the row points at the run that most recently produced it.

Versioning every run was considered and rejected: it preserves history nobody has asked for, grows storage with each reprocess, and makes "which artifact is current?" a database query rather than a known address. If history is ever wanted, S3 bucket versioning provides it at the storage layer with no application complexity — the correct place for it, rather than encoding versions into keys.

### 7. Artifact type is discriminated by file extension, not a path segment

The artifact key is `artifacts/{account_id}/{document_id}.md`, not `artifacts/{account_id}/{document_id}/{artifact_type}.md`.

`ArtifactType` currently has exactly one member, so a dedicated path segment discriminates between one thing. The segment form also renders as `markdown.md`, stating the type twice. The flat form makes both key schemes symmetric — `raw/{account_id}/{document_id}.pdf` and `artifacts/{account_id}/{document_id}.md` differ in exactly one segment.

The extension is hardcoded as `.md` while `ArtifactType` has a single member. A type-to-extension mapping is only worth introducing when a second type exists, and introducing one now would be a lookup table with one entry.

This does not discard the discriminator; it moves it to the extension, which is its conventional home. The arrangement holds under one invariant: **artifact types must map to distinct file extensions.** `MARKDOWN → .md`, `HTML → .html`, `JSON → .json` all satisfy it. It would break only if two types shared an extension, where the database would permit two rows under `unique(document_id, artifact_type)` while both derived keys collided in S3 — two rows silently referencing one object. Recorded as an invariant to respect when adding a type, not defended against now.

The folder form's one concrete advantage — listing all of a document's artifacts with a single S3 prefix query — is unused: `ArtifactRepository.list_by_document_id` answers that from Postgres, which is the index.

### 8. Raw key construction moves from the route into `DocumentService`

`api/routes/documents.py:34` currently builds the storage key inside an HTTP handler. A key format is a storage concern, not a request-handling one, and the route has no business knowing it.

The move is forced anyway: the document's UUID must be generated before the insert, and generating an identifier is service-layer work. Since the service must now produce the ID, and the key derives from it, both belong together. The route drops to passing `account_id`.

Artifact key construction already lives in `ProcessingService` and stays there.

### 9. Migrations truncate explicitly rather than relying on an empty database

Postgres cannot cast an integer to a UUID, so no migration in this design can preserve existing rows. `make nuke` makes that acceptable.

Each migration nevertheless issues an explicit `TRUNCATE` before altering column types, rather than quietly depending on being run against a freshly nuked database. On an empty database this is a no-op; on a populated one it fails loudly and predictably instead of erroring mid-`ALTER` with a cast error. The destructiveness is stated in each migration's docstring.

`downgrade()` reverses the schema and is equally destructive; its docstring says so rather than implying a round trip.

The `one_active_job_per_document` partial index must be dropped before and recreated after the `document_id` type change — Postgres will not alter a column type underneath an index.

### 10. No content-hash deduplication

Caching derived output on a hash of `(content, parser_version)` is a mainstream pattern for expensive derivations — build systems, Docker layers, and OCR pipelines all do it — and re-parsing an identical PDF is genuinely wasted CPU.

It is rejected because it would defeat this project's purpose. A load generator uploads the same fixture PDF thousands of times; with content-hash caching, all but the first become instant no-ops that never reach a worker. The CPU-bound parse is the load being measured, and deduplicating it would measure the cache instead of the pipeline. The "wasted" CPU is the payload.

Should this ever serve real users who re-upload, the note worth keeping is that `head_object` — already called in `JobService.create` — returns S3's `ETag`, which for single-part uploads is the MD5 of the content, giving a free content fingerprint from an existing call. For multipart uploads the `ETag` is a hash-of-hashes with a `-N` suffix and is not a usable content hash.

## Components

**`shared/infrastructure/models.py`** — `Document.id`, `Job.id`, `Artifact.id` to `UUID` primary keys, each with `default=uuid4` so SQLAlchemy generates the value client-side at insert; `Job.document_id`, `Artifact.document_id`, `Artifact.job_id` to `UUID` foreign keys; `Document.file_name` removed; `Artifact.object_key` loses `unique=True`; `Artifact` gains a `UniqueConstraint("document_id", "artifact_type")`.

The `default=uuid4` on `Document.id` is retained even after Phase 2 moves generation into `DocumentService`. Once the service passes an explicit `id` the default never fires for that path, but it keeps every other insert path — tests, future CLI commands — from having to know that IDs are caller-supplied.

**`shared/migrations/versions/`** — three new revisions, one per phase (identifiers, `file_name` removal, artifact constraint).

**`shared/dtos/`** — `DocumentDTO.id`, `CreateDocumentDTO` (gains `id`, loses `file_name`), `JobDTO.id`/`.document_id`, `CreateJobDTO.document_id`, `ArtifactDTO.id`/`.job_id`/`.document_id`, `CreateArtifactDTO.job_id`/`.document_id` all to `UUID`.

**`shared/interfaces/`** — repository and service protocol signatures updated to `UUID`.

**`shared/infrastructure/repositories/document.py`** — `create` accepts a caller-supplied `id`; `get_by_id` takes a `UUID`.

**`shared/infrastructure/repositories/artifact.py`** — `create` becomes an upsert on `(document_id, artifact_type)`; `list_by_document_id` takes a `UUID`.

**`shared/infrastructure/repositories/job.py`** — `UUID` signatures throughout.

**`api/services/document.py`** — generates the document `UUID`, builds `raw/{account_id}/{document_id}.pdf`, passes both to the repository.

**`api/routes/documents.py`** — key construction removed; `POST /documents` loses its request body; path parameters become `UUID`.

**`api/routes/jobs.py`** — `document_id` and `job_id` path parameters become `UUID`.

**`api/schemas/requests/documents.py`** — `CreateDocumentRequest` removed (no body).

**`api/schemas/responses/documents.py`** — `CreateDocumentResponse.document_id` and `DocumentResponse.id` to `UUID`; `DocumentResponse.file_name` removed; `ArtifactResponse.id` to `UUID`.

**`api/schemas/responses/jobs.py`** — `JobResponse.id` and `.document_id` to `UUID`.

**`api/services/job.py`** — `UUID` signatures; publishes `job_id` as a string.

**`worker/services/processing_service.py`** — artifact key becomes `artifacts/{account_id}/{document_id}.md`; `Path(document.file_name).stem` removed. The `account_id` comes from `job.account_id`, which the service already has in hand — `artifacts` has no `account_id` column of its own and does not gain one.

**`worker/infrastructure/messaging/consumer.py`** — parses `job_id` from the message payload as a `UUID`.

## Phases

**Phase 0 — Baseline.** Complete. `make test` green and one full upload → process → download cycle confirmed working, establishing a reference point for later phases.

**Phase 1 — UUID identifiers.** Migration A converts all six columns, dropping and recreating the foreign keys and the `one_active_job_per_document` partial index around the alters. The type propagates through DTOs, interfaces, repositories, services, routes, schemas, the RabbitMQ payload, and the consumer.

IDs are generated by `default=uuid4` on the models in this phase, so no caller has to supply one and the existing insert paths keep working unchanged. Key formats are untouched — the `uuid4()` nonce and `file_name` remain in keys — which keeps this phase a pure type change and independently verifiable.

**Phase 2 — Raw key and `file_name` removal.** Migration B drops `documents.file_name`. `CreateDocumentRequest` is removed, `DocumentResponse.file_name` is removed, key construction and UUID generation move into `DocumentService`, and the raw key becomes `raw/{account_id}/{document_id}.pdf`. The `uuid4()` nonce disappears.

**Phase 3 — Artifact key, constraint, and upsert.** Migration C drops `unique(object_key)` and adds `unique(document_id, artifact_type)`. The artifact key becomes `artifacts/{account_id}/{document_id}.md` and `ArtifactRepository.create` becomes an upsert.

**Phase 4 — Verification.** A full end-to-end run compared against the Phase 0 baseline, plus a deliberate reprocess of the same document to exercise the upsert against real Postgres and MinIO rather than only mocks.

Each phase ends with `make test` green. Migrations are destructive, so phase boundaries require `make nuke && make setup`.

## Testing

Tests are written within each phase, not deferred to the end.

Updated: every test carrying an integer identifier — `tests/unit/api/routes/test_documents.py`, `test_jobs.py`, the four service tests under `tests/unit/api/services/`, `tests/unit/worker/services/test_processing_service.py`, `tests/unit/worker/infrastructure/messaging/test_consumer.py`, and all four repository suites under `tests/integration/repositories/`.

New coverage:

- The raw key matches `raw/{account_id}/{uuid}.pdf` and contains no client-supplied text.
- The artifact key matches `artifacts/{account_id}/{document_id}.md`.
- `POST /documents` succeeds with no request body.
- A malformed UUID in a path returns 422.
- **Upsert behaviour:** processing the same document twice leaves exactly one `artifacts` row, with an unchanged `object_key` and an updated `job_id`. Written at both levels — unit with a mocked repository, and integration against real Postgres, since the constraint itself is what is being verified and a mock cannot confirm it.

## Open Questions

None. All decisions taken during design; the extension-uniqueness invariant in Design Decision 7 is the only constraint deferred to a future change.

## Future Work

**Document lifecycle.** The gap that prompted this design remains open: `POST /documents` commits a row before any upload occurs, `documents` has no status column, no cleanup mechanism exists, and an expired presigned URL cannot be regenerated — a client must call `POST /documents` again, permanently stranding the previous row. The shape of the fix is a status column (`PENDING` → `UPLOADED` → …), a `POST /documents/{id}/complete` endpoint verifying via `head_object`, and a reaper deleting stale `PENDING` rows. An S3 lifecycle rule on the `raw/` prefix would cover the storage side declaratively.

**Presigned-URL refresh, `DELETE /documents/{id}`, and `Idempotency-Key`.** Each closes a distinct way to strand rows: expiry, client-initiated cancellation, and network-retry duplication respectively.

**S3 bucket versioning.** The correct mechanism should artifact history ever be wanted, in preference to encoding versions into keys.

**Document-level status.** A coarse `status` on `GET /documents/{id}` answering "is it ready?", leaving job-level detail for "what happened?". Pairs naturally with the lifecycle status column. Deliberately not built now: job-level polling exposes attempts, queue delay, and processing latency, which is exactly what load testing needs to observe.

**UUIDv7.** Worth revisiting on Python 3.14, or if benchmarks ever implicate index insert locality.
