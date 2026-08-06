# Security and privacy

This project assumes the repository will be public and the inference endpoint will be private.

## Data that never belongs in tracked content

- API keys, bearer tokens, cookies, private keys, or environment-file contents;
- private network addresses, internal domains, machine names, account names, or topology;
- absolute user-directory paths, inventory IDs, serial numbers, MAC addresses, or screenshots;
- raw prompts, completions, reasoning, tool arguments, traces, logs, or packet captures; and
- real model-run artifacts copied from a private environment.

A leaderboard submission is a narrow exception for reviewed public product details. Its closed
contract permits the CPU model and logical cores, system memory and architecture, accelerators used
for inference, execution mode, runtime name, version, and backend, plus an optional closed snapshot
of context window, concurrency, speculative decoding, and offload mode. Unknown configuration is
represented explicitly rather than inferred. It does not permit a hostname, account, address,
device UUID, serial number, inventory tag, unused device list, or free-form note.

Examples use loopback, `example.com`, and standards-reserved documentation addresses. Local values
belong in ignored files under `.local/` or in process environment variables.

## Three publication barriers

1. **Local privacy gate**: scans the exact staged index before commit and the complete tracked tree
   before push. It checks generic identifier patterns, current machine/account identifiers collected
   at runtime, dangerous file types, symlinks, and an ignored custom literal denylist.
2. **Secret scanner**: Gitleaks runs locally and in continuous integration with redacted output.
3. **Host protection**: GitHub secret scanning and repository push protection are enabled on the
   public repository.

Continuous integration is a backstop, not a confidentiality boundary: content has already reached the
host by the time CI sees it. Keep the local hooks installed.

## Local denylist

Run `scripts/install-hooks` once per clone. It creates `.local/privacy-denylist.txt` from the
comments-only example with owner-only permissions where supported. Add one literal identifier per
line, including private project codenames, host labels, internal domains, and other values that a
generic scanner cannot recognize. Do not put credentials in this file.

Strict publication checks fail closed if the denylist is missing, empty, tracked, not covered by a
Git ignore rule, or group/world-accessible. Findings report only rule, path, and line number. They
never print the matched value. This makes a new clone establish its own environment boundary before
publication.

## Credential handling

The reference runner accepts a credential from the environment name declared by the local manifest.
An optional env file is a path argument, not a secret argument, and must be owner-only on platforms
that expose POSIX modes. Credentials are held in memory only for the request and are never reported.
Endpoints containing URL credentials, query strings, fragments, public addresses, or unresolved
names are rejected.

## Result minimization

Run artifacts are ignored and owner-only where supported. They contain model provenance, aggregate
usage/performance, categorical routing, and boolean checks. They do not contain the text used to
derive those values or a reusable fingerprint of that text. A repeatability experiment may compare
responses transiently and retain only a stability boolean.

## Leaderboard submission boundary

The leaderboard exporter accepts only a fully valid current-standard report. It combines one model
result with a separate public environment descriptor and writes one candidate per model. The
descriptor must be a regular, non-symlink file that Git ignores. It must be owner-only on systems
that expose POSIX modes.

The candidate removes the source run ID and time, manifest digest, local model selector, contributor,
raw content, per-case timing, and per-case token counts. It keeps public model provenance, settings,
exact hardware and runtime fields, optional reported runtime configuration, categorical case
outcomes, and rounded aggregate performance.
The content digest detects changes and duplicates. It does not prove that the benchmark was run.

The Pages file picker reads only an already-prepared candidate. Its shape check runs in the browser,
does not upload the file, and is not a replacement for the Python validator, privacy gate, or review.

Before deliberately publishing a result:

1. put the exact public hardware and runtime details in `.local/hardware.json`;
2. prepare the candidate with `litb prepare-submission`;
3. read the entire candidate and decide whether its hardware and performance could identify the
   setup more closely than intended;
4. add only the candidate to `site/data/submissions/` and rebuild the leaderboard;
5. run the full privacy and secret scans; and
6. use the base-controlled exact-head review lane, with maintainer review when automation reports a
   finding or cannot establish every gate.

The guided `litb run --submission pr` path automates steps 2 through 5 without weakening them. Hosted
automation performs step 6 only for an exact benchmark-only change; every other change stays manual.
The `litb publish-submission --candidate <path>` retry applies the same gates to an existing
canonical, owner-only, ignored minimized file, so a failed public step does not require another
inference run.
The post-run path always writes the private aggregate report first and saves the minimized candidate;
both paths show the entire candidate, name the public GitHub account, and require an explicit
publication confirmation. Both require the strict local denylist and Gitleaks before any mutating
GitHub call.

Publication uses a fixed canonical target and an isolated temporary clone. Only one validated
candidate and the generated leaderboard may enter the Git index or GitHub API payload. The raw
report, descriptor, endpoint, credentials, environment, artifact directory, and denylist never enter
the network helper. Validation children receive a scrubbed environment so inference credentials and
scanner configuration overrides are not inherited. Upload bytes are read back from the checked Git
index, never from a potentially changed working tree. The helper creates a feature branch and pull request; it does not write
to `main`, force-push, or overwrite an existing branch. A contributor without upstream write access
gets a public fork, which is disclosed before confirmation.

An idempotent retry trusts an existing pull request only after verifying its base and head identity,
exact two-file diff, and exact candidate and leaderboard bytes. Hosted benchmark-boundary checks run
the validator stored at the pull request's trusted base commit, so a data PR cannot relax its own
checker. Candidate save paths inside a worktree must be Git-ignored before a file or directory is
created.

The trusted benchmark boundary executes only validator and builder code from the base commit. It
fetches the pull-request head as Git data, verifies the exact append-only paths and ordinary blob
modes, materializes only public dataset blobs, and checks schema, digest, duplicates, and the
byte-exact leaderboard before posting one fixed audit marker. No pull-request code is checked out or
executed in the privileged workflows.

The marker contains no contributor-controlled text and binds the full base and head SHAs. The
downstream workflow fetches it by the exact comment ID and requires the canonical body, equal
creation/update timestamps, GitHub Actions user ID `41898282`, and GitHub App ID `15368`. The marker
is audit evidence that trusted classification completed; it is not authorization by itself. After
the marker job succeeds, the base-controlled caller directly invokes a local reusable workflow from
the same trusted commit and passes the exact PR number, full base SHA, full head SHA, and comment ID.
The called workflow independently verifies every input and the live marker before repeating the
complete authorization.

The required branch-protection context named `Trusted benchmark boundary` comes from a final
aggregator, not the early classifier. It remains pending until the marker and reusable automation
jobs reach their exact expected states. Consequently, an approval or auto-merge request left by an
interrupted attempt cannot merge the pull request through an already-successful early check.

Comments created with a repository `GITHUB_TOKEN` do not start downstream `issue_comment` workflow
runs, so the lane no longer depends on a clean Codex reply as its trigger or merge gate. Codex and
CodeRabbit remain best-effort advisory reviewers, and automation does not wait for them. Their clean,
missing, failed, skipped, or rate-limited response never authorizes a merge. A review thread or
changes request visible during final revalidation still fails closed.

Before any reviewer credential is bound, trusted code rechecks the live PR, content boundary,
publicly observable app-bound required checks, native review decision, review states, complete
paginated thread set, exact marker, and exact base/head. GitHub enforces the repository's remaining
configured protections. The workflow does not claim per-run visibility into administration-only
settings; the read-only Actions identity may omit `allow_auto_merge` even when native auto-merge is
enabled. Native auto-merge, stale-review dismissal, last-push approval, conversation resolution,
linear history, admin enforcement, and force-push/deletion prohibitions are mandatory operator
prerequisites. After the narrowly scoped reviewer credential is bound, the workflow requires an
authoritative `allow_auto_merge: true` response immediately before each possible mutation. If native
auto-merge is disabled or cannot be confirmed there, the final required boundary remains failed.
The caller explicitly maps repository secret `ERNEST_REVIEW_TOKEN` to the local reusable workflow's
`reviewer_token`; `secrets: inherit` is forbidden, and the credential is bound only in the final
mutation step. The workflow arms native squash auto-merge with a full-head guard and fixed
digest-derived commit metadata before adding a full-head approval. It freshly requires the live
`main` tip to equal the authorized base SHA immediately before either possible mutation. It never
performs a direct merge, admin bypass, head checkout, force-push, or push to `main`.

The automated lane requires `litb/submission-<submission-id>` as the live head ref, with the digest
matching the sole added file and canonical content ID. GitHub's transient unknown mergeability gets
only bounded retries. Once mergeability is established, an `unstable` state may continue to native
auto-merge, but it does not pass or waive a required check; GitHub remains the merge authority.
The `litb/submission-` namespace is reserved: if a branch bearing that name changes into a general,
mixed, or otherwise non-submission diff, the trusted boundary fails instead of reclassifying it as a
normal code pull request.
After a partial run, an existing approval is reusable only if it is the configured reviewer's latest
decisive state for the exact current head. Full revalidation precedes re-arming missing auto-merge
while the final required boundary remains pending. That pending required context keeps the exact
retry eligible for native auto-merge rather than presenting GitHub with an already-clean approved
pull request. A later dismissal, change request, or approval of another commit fails closed.

The pull request is public before continuous integration finishes. The candidate has no contributor
field, but the submitting GitHub account remains visible. Accepted entries are self-reported,
schema-validated, exact-head reviewed, and not independently reproduced. Deterministic validation
establishes schema conformance and integrity of the published bytes. The digest, audit marker, bot
review, and approval establish neither provenance nor attestation that a run occurred.
The reviewer-account approval is an automated policy gate, not a second independent substantive
review.

For that reason the project calls the record **identifier-minimized**, not anonymous. Exact model,
hardware, runtime, runtime configuration, and performance data can still fingerprint a setup, while GitHub adds the account
and publication time. Cancellation, end-of-input, an invalid choice, a missing tool, a stale
leaderboard base, or a failed local gate causes no branch or PR creation. If PR creation fails after
the branch exists, the command reports the exact public branch that may remain instead of claiming a
rollback.

## If a leak is detected

Stop publishing. Rotate an exposed credential first, then remove the data from the branch and hosted
history. Do not paste the value into an issue, pull request, chat, or scanner log. Follow the hosting
provider's sensitive-data removal process and document only the category and remediation status.
