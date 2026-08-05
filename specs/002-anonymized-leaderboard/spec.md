# Feature specification: Anonymized benchmark leaderboard

**Feature Branch**: `002-anonymized-leaderboard`

**Created**: 2026-08-05

**Status**: Implemented

**Input**: Add a GitHub Pages site with a brief explanation, an anonymized leaderboard, and a safe
way for people to prepare and submit benchmark results. Add the author's reason for building the
test bench to the README.

## User scenarios and testing

### User story 1: Read the leaderboard (Priority: P1)

A visitor lands on a small public site, learns what the test bench measures, and reaches the
leaderboard without working through a long product page. The table shows model provenance, the
hardware and runtime used for inference, task and format scores, and observed performance.

**Why this priority**: The site exists to make accepted results easy to inspect.

**Independent test**: Serve the static site with an empty dataset and with several fixture entries.
Confirm that the explanation, ranking method, privacy note, empty state, filters, and table all work
without a framework or third-party service.

**Acceptance scenarios**:

1. **Given** accepted standard-profile entries, **When** the page loads, **Then** it shows them in a
   quality-ranked table with the hardware and runtime needed to interpret latency and throughput.
2. **Given** entries with the same semantic and exact-format scores, **When** ranks are assigned,
   **Then** the entries share a rank and speed does not break the tie.
3. **Given** no accepted entries, **When** the page loads, **Then** it shows an honest empty state and
   a link to the submission process.
4. **Given** a string that contains HTML syntax, **When** a row is rendered, **Then** the browser
   treats it as text rather than markup.

---

### User story 2: Prepare an anonymized submission (Priority: P1)

An operator can turn a valid standard benchmark report plus a closed public hardware descriptor into
one minimized public record per model. The export removes local correlation fields and refuses a
report or descriptor that is not comparable or does not pass the existing privacy checks.

**Why this priority**: A public leaderboard is only useful if its submission boundary is clear and
repeatable.

**Independent test**: Export synthetic valid, limited, invalid, smoke, single-model, and multi-model
reports. Verify the accepted files contain only the closed public contract and that every rejected
case fails without echoing sensitive values.

**Acceptance scenarios**:

1. **Given** a valid standard report with verified model identity, **When** the operator exports it,
   **Then** the tool combines it with the public hardware descriptor and writes one closed submission
   record per selected model.
2. **Given** a smoke, limited, invalid, or identity-unverified report, **When** export is attempted,
   **Then** the tool refuses it and does not create a submission.
3. **Given** an eligible report, **When** it is exported, **Then** the result retains bounded hardware
   product and runtime details but omits the run identifier, timestamp, local model selector,
   manifest digest, endpoint, environment, host identity, serial and inventory identifiers, and
   contributor identity.
4. **Given** an exported record on the Pages submission screen, **When** the visitor selects it,
   **Then** validation and preview happen in the browser without uploading the file.
5. **Given** a prepared record, **When** the visitor continues, **Then** the site directs them to a
   reviewed pull-request workflow and explains that their GitHub account remains visible there.

---

### User story 3: Review and publish entries (Priority: P2)

A maintainer can validate submitted JSON, reject duplicates or unsupported records, generate the
public dataset deterministically, and deploy the site from the default branch.

**Why this priority**: GitHub Pages is static, so repository review is the publication boundary.

**Independent test**: Add valid, duplicate, malformed, oversized, and privacy-unsafe fixtures in a
temporary submission directory. Confirm that only valid unique entries produce a stable leaderboard
dataset and that Pages deployment runs only from the default branch.

**Acceptance scenarios**:

1. **Given** a pull request containing a valid record, **When** continuous integration runs, **Then**
   the closed schema, content digest, privacy rules, eligibility, and dataset build all pass.
2. **Given** a duplicate, renamed, malformed, unknown-field, or out-of-range record, **When** it is
   validated, **Then** publication fails with a categorical error that does not echo submitted data.
3. **Given** accepted records on the default branch, **When** the Pages workflow runs, **Then** it
   builds the public dataset and deploys only the static site directory.
4. **Given** a community result, **When** it appears on the site, **Then** the site calls it
   self-reported, schema-validated, maintainer-reviewed, and not independently reproduced.

### Edge cases

- A report contains more than one eligible model.
- A run uses only a CPU, shared memory, an accelerator row with a count greater than one, or a
  hybrid CPU and accelerator configuration.
- Two distinct entries earn the same quality score.
- Usage data is absent, so throughput is unavailable.
- A contributor renames a submission file or changes content without updating its digest.
- A model name contains markup, control characters, a local identifier, or an unusually long value.
- A submission uses a supported schema but an unsupported suite or profile.
- The dataset is empty, missing, malformed, or unavailable to the browser.
- A visitor has JavaScript disabled or uses a narrow screen.
- A pull request is public before its checks finish.

## Requirements

### Functional requirements

- **FR-001**: The repository MUST publish a static GitHub Pages site from a dedicated site directory.
- **FR-002**: The first page MUST give a brief explanation and place the anonymized leaderboard
  immediately after it.
- **FR-003**: The site MUST work without third-party scripts, fonts, analytics, cookies, or a write
  credential.
- **FR-004**: The leaderboard MUST rank eligible entries by semantic score and then exact-format
  score, with dense ties.
- **FR-005**: Latency and throughput MUST be displayed with their hardware and runtime context and
  MUST NOT affect quality rank.
- **FR-006**: The site MUST identify records as self-reported and not independently reproduced.
- **FR-007**: The site MUST render all record strings through text-only DOM operations.
- **FR-008**: The site MUST provide a useful empty and load-error state.
- **FR-009**: The command-line tool MUST export one minimized record for each selected eligible model
  and MUST require a separate public hardware descriptor.
- **FR-010**: Export MUST call the existing closed run-record validator before reading result fields.
- **FR-011**: Export MUST accept only the current standard profile, an overall valid report, verified
  model preflight, matching runtime identity, a valid model result, and the complete standard case set.
- **FR-012**: A submission MUST retain only public model provenance, public generation settings,
  structured hardware and runtime context, minimized categorical case outcomes, and rounded
  aggregate quality and performance observations.
- **FR-013**: A submission MUST omit the source run identifier and time, local model selector,
  manifest digest, endpoint, credentials, environment, operating-system account, hostname, network
  data, serial number, inventory ID, device UUID, unused device inventory, contributor identity, raw
  prompts, completions, reasoning, and tool arguments.
- **FR-014**: Every submission MUST have a deterministic SHA-256 identifier derived from its canonical
  content, excluding the identifier field itself.
- **FR-015**: The validator MUST require an exact filename based on the submission identifier and
  MUST reject duplicate identifiers.
- **FR-016**: Submission and dataset contracts MUST be closed, bounded, and versioned.
- **FR-017**: The Pages submission screen MUST inspect only an already-minimized record and MUST NOT
  upload, transmit, or accept a raw run report.
- **FR-018**: Publication MUST use a reviewed pull request. The documentation MUST state that the
  pull request and its GitHub account are public even though the JSON record has no contributor field.
- **FR-019**: Continuous integration MUST validate all accepted records and build the dataset before
  a change can be treated as publishable.
- **FR-020**: The Pages workflow MUST deploy only from the default branch with pinned actions and
  minimal `contents: read`, `pages: write`, and `id-token: write` permissions.
- **FR-021**: The README MUST explain in the author's voice that the project began as a way to compare
  how local models handled a fixed set of tasks on the author's own hardware.
- **FR-022**: README, site, submission, security, and contribution documentation MUST agree on the
  privacy boundary and ranking method.
- **FR-023**: The public hardware descriptor MUST record the CPU model and logical core count, system
  memory and memory architecture, the accelerator devices used for inference, execution mode, and a
  bounded runtime name, version, and backend.
- **FR-024**: The hardware descriptor MUST use a closed versioned schema, remain ignored and
  owner-readable locally, and contain no free-form notes or general machine inventory.

### Key entities

- **Leaderboard submission**: One identifier-minimized benchmark result for one public model artifact
  and one fixed standard-suite configuration.
- **Submission identifier**: A deterministic digest of canonical submission content.
- **Leaderboard case**: A case identifier plus categorical outcome, termination, and route fields.
- **Hardware descriptor**: Structured public product details for the CPU, system memory,
  accelerators used during inference, execution mode, and runtime.
- **Leaderboard dataset**: The deterministic collection of accepted records with quality-only ranks.
- **Submission review**: The public pull request and automated checks used before an entry is accepted.

## Success criteria

### Measurable outcomes

- **SC-001**: One hundred percent of accepted submission files validate against the runtime contract
  and the published JSON Schema.
- **SC-002**: Export tests prove that every field listed in FR-013 is absent from generated records.
- **SC-003**: Ranking fixtures prove quality ordering and dense ties without using performance values.
- **SC-004**: Browser tests or equivalent DOM checks prove that untrusted record strings cannot add
  markup or script execution.
- **SC-005**: The full Python test suite and publication gate pass on Linux, macOS, and Windows.
- **SC-006**: The deployed Pages workflow completes its record validation, deterministic build,
  artifact upload, and deployment jobs successfully.
- **SC-007**: The live site loads the empty or populated leaderboard and exposes a working submission
  path without sending the selected JSON to a remote service.

## Assumptions

- GitHub Pages remains a static host. It does not receive benchmark writes directly.
- Community entries are honest self-reports. Schema validation and review do not prove that a model
  produced the submitted measurements.
- Hardware combinations and performance values can weakly characterize a private setup. Contributors
  review the minimized JSON and choose whether to publish those details.
- The first leaderboard accepts only the current standard suite. Future suite versions require an
  explicit contract and ranking change.
- Accepted submission files are append-only. Corrections use a new reviewed record rather than an
  unreviewed rewrite.
