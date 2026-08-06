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

**Decision**: The Pages submission screen accepts only the minimized submission format, parses it as
strict JSON with duplicate-member rejection, applies the parallel closed validator, recomputes its
canonical payload-minus-ID digest, and renders a preview using text-only DOM APIs. Copy and download
actions remain local to the browser. The same byte-oriented decoder and strict parser handles every
fetched leaderboard monolith, index, and shard; fatal UTF-8 errors and byte-order marks are rejected
before transport validation.

**Rationale**: Contributors can review what they are about to publish and catch raw-JSON or integrity
drift without giving the site a write token or sending a private run report to another service. The
Python validator and pull-request boundary remain authoritative.

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

## Decision 8: Bump new evidence without rewriting legacy records

**Decision**: Require schema `1.1` for new submissions, retain accepted `1.0` bytes and digests, and
annotate legacy rows only in a mixed projection as `legacy_unreported` with absent month and
condition evidence. Keep transport `index_version` at `1.0`.

**Rationale**: Rewriting accepted files would break their content identities. Synthesizing fields
would falsely claim measurements that never occurred. Independent transport versioning avoids an
unrelated Pages migration.

**Alternatives considered**:

- Continue accepting `1.0` was rejected because callers could invisibly omit comparable validity and
  recency.
- Rewrite or rehash historical submissions was rejected because accepted evidence is append-only.
- Treat legacy rows as clean was rejected because absence of evidence is not clean evidence.

## Decision 9: Use month-only recency and categorical measurement conditions

**Decision**: Publish the source report's UTC month plus closed pre/post threshold outcomes and
categories from an ignored owner-only sidecar. Optional determinism is limited to aggregate rates,
booleans, and a closed verdict. Bind the sidecar to exactly one report with a required
`source_run_id`, require exact equality with `report.run_id`, and bound its unique model rows to
1–1000. The run binding remains local and is not part of the public schema.

**Rationale**: Runtime versions age, so no date at all impairs interpretation. Month resolution has
substantially less reidentification entropy than an event timestamp. Closed categorical conditions
support comparison without exposing raw host telemetry.

**Alternatives considered**:

- A precise timestamp was rejected as unnecessary correlation data.
- No recency field was rejected because runtime/version results become misleading with age.
- Raw sampler output or free text was rejected as fingerprinting and reviewer-injection surface.
- Unbound evidence, a caller-selected stale run, and an unbounded model list were rejected because
  they weaken the local categorical handoff or its resource bounds without adding public value.

## Decision 10: Add one facet seam and a precommitted graduation rule

**Decision**: Parameterize ranking with a facet selector but ship only `all-cases-text`. Name the
version `1.0` configuration dimensions once and record, without consuming, a graduation threshold of
25 entries across five model families.

**Rationale**: Future capability views and config-cell aggregation should be additive. Fixing the
minimum sample rule before results arrive avoids tuning it after observing favorable data.
Minimized submissions retain full-suite aggregate performance only, so subset selectors suppress
latency and throughput rather than mislabeling those aggregates as facet-specific measurements.

**Alternatives considered**:

- Capability pages now were rejected because roughly one binary case per task carries no useful
  discriminating precision.
- An inline unversioned config tuple was rejected because collapse and filtering would drift.
- Enforcing the graduation policy now was rejected because no additional facet ships in this stage.
