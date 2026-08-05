# Research: Anonymized benchmark leaderboard

## Decision 1: Use reviewed repository submissions

**Decision**: GitHub Pages stays static. Contributors prepare a minimized file and submit it through
a pull request.

**Rationale**: A static site cannot safely write to the repository without a backend or a credential.
A pull request gives maintainers a diff, automated checks, and public review before an entry joins the
dataset.

**Alternatives considered**:

- A token embedded in browser code was rejected because every visitor could recover and misuse it.
- A direct form backed by a new service was rejected because it adds account, storage, abuse, and
  privacy surfaces that the project does not need.
- Automatic ingestion from an issue was rejected because unreviewed text would need write-capable
  automation and would be public before validation.

## Decision 2: Export a smaller record

**Decision**: The exporter starts with the validated run record, adds a separate closed hardware and
runtime descriptor, keeps categorical task results and rounded aggregate performance, then removes
local and correlating fields.

**Rationale**: The leaderboard needs enough evidence to identify the public model artifact, score the
fixed tasks, and interpret speed on the hardware that performed the run. It does not need the run
UUID, time, local selector, manifest hash, endpoint, hostname, serial number, inventory ID, unused
devices, or contributor.

**Alternatives considered**:

- Publishing the original report was rejected because it carries fields that have no leaderboard
  purpose and can correlate a public entry with a private run.
- Retaining a hash of the source report was rejected because it would preserve that correlation
  without proving that the report is genuine.
- Accepting free-form notes was rejected because they are difficult to anonymize and render safely.

## Decision 3: Use a closed hardware descriptor

**Decision**: A separate ignored JSON file records the CPU model and logical cores, system memory and
memory architecture, accelerators used for inference, execution mode, and bounded runtime details.

**Rationale**: Hardware is necessary to interpret observed latency and throughput. Keeping it in a
separate descriptor preserves the existing run-record contract and makes the exact public fields easy
to review before export.

**Alternatives considered**:

- Omitting hardware was rejected because speed without its execution context is not useful.
- Collecting hardware automatically was rejected because inventory APIs can expose serial numbers,
  device UUIDs, host labels, unused devices, and other details that do not belong in a public record.
- A free-form system description was rejected because it is difficult to validate and easy to fill
  with lab identifiers.

## Decision 4: Use a canonical content identifier

**Decision**: The submission ID is the SHA-256 digest of canonical JSON with the ID field omitted.

**Rationale**: The digest gives each exact minimized result a stable filename, catches accidental
content changes, and makes exact duplicates easy to reject. The exporter normalizes fields whose
contract type is `number` before hashing, so equivalent spellings do not create different
identifiers. Integer-only fields retain their stricter JSON type.

**Alternatives considered**:

- Random identifiers were rejected because they allow identical content to be submitted repeatedly.
- Contributor-based identifiers were rejected because the JSON record must not identify a person or
  organization.
- A signed attestation was deferred. The project has no shared signing service or hardware trust
  model, and a signature would still not prove the model produced the result.

## Decision 5: Rank quality only

**Decision**: Semantic pass rate is the first ranking key, exact-format pass rate is the second, and
equal quality results share a rank. Latency and throughput are displayed but never used to order ties.

**Rationale**: Each row has enough context to interpret its speed, but results from different systems
are still observations rather than controlled comparisons.

**Alternatives considered**:

- A blended quality and speed score was rejected because its weighting would be arbitrary and would
  reward undisclosed hardware differences.
- Throughput as a tie-breaker was rejected for the same reason.
- A blended cross-hardware score was deferred because it would require a defensible normalization
  model that the current suite does not have.

## Decision 6: Inspect files in the browser without uploading

**Decision**: The Pages submission screen accepts only the minimized submission format, validates its
basic closed shape, and renders a preview using text-only DOM APIs. Copy and download actions remain
local to the browser.

**Rationale**: Contributors can review what they are about to publish without giving the site a write
token or sending a private run report to another service.

**Alternatives considered**:

- Accepting a raw run report in the browser was rejected because two independent exporters could
  drift and because the raw report contains fields the site does not need.
- Third-party form, table, analytics, and font services were rejected because they add network
  requests and weaken the simple privacy claim.

## Decision 7: Treat entries as self-reported

**Decision**: The site describes accepted records as self-reported, schema-validated,
maintainer-reviewed, and not independently reproduced.

**Rationale**: Closed schemas and arithmetic checks can catch malformed data. They cannot prove that
a model ran or that a contributor left values unchanged before submission.

**Alternatives considered**:

- Calling accepted entries verified was rejected because review verifies the publication contract,
  not the physical experiment.
- Running submissions on hosted hardware was rejected because the project tests local inference and
  intentionally does not manage model artifacts or infrastructure.
