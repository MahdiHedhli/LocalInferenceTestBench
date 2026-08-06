# Contributing

Contributions are welcome when they keep the baseline portable, safe, and easy to audit.

## Start with the specification

This project uses [GitHub Spec Kit](https://github.com/github/spec-kit) v0.16.0. Read the constitution
and active feature under `specs/` before changing behavior. Update the spec, plan, contracts, and tasks
when a change alters the CLI, manifest, report schema, publication boundary, or experimental scope.

## Local setup

1. Use Python 3.11 or newer.
2. Install the tracked hooks with `scripts/install-hooks`.
3. Replace the commented shapes in the generated `.local/privacy-denylist.txt` with private,
   non-secret literals from your environment; keep the file ignored and owner-only.
4. Install Gitleaks 8.30.1 or newer.
5. Run `./scripts/public-check --full-tree --strict` before opening a pull request.

Never put a real credential or realistic secret in a test fixture. Tests should synthesize patterns
that the scanner recognizes without creating a usable token.

## Design rules

- Keep the core standard-library-only and OpenAI-compatible.
- Put runtime lifecycle or hardware collectors behind optional adapters.
- Keep specialized model families and dynamic agent benchmarks under `docs/experiments/`.
- Add tests for scoring, endpoint safety, manifest/schema changes, and output minimization.
- Do not persist prompts, responses, reasoning, tool arguments, endpoint values, or general machine
  inventory. A reviewed leaderboard submission may contain only the closed public hardware fields.
- Use standards-reserved examples and non-identifying fixture names.

## Submit a benchmark

Benchmark submissions use a public pull request. Before opening one, read
[submitting a benchmark](docs/submitting-benchmarks.md) and the
[security and privacy guide](docs/security-and-privacy.md).

1. Run the current `standard` profile and confirm that the report is valid.
2. Copy `config/hardware.example.json` to `.local/hardware.json`, restrict it to owner access, and
   enter the exact hardware used for inference plus the serving runtime and its known configuration.
3. Choose the public-PR option after a valid interactive standard run, or run
   `litb run ... --submission pr --confirm-public --submission-model <report-model-id>` for an
   explicit non-interactive flow. The model selection is required when the report contains more
   than one model and may be omitted for a single-model run.
4. Read the complete identifier-minimized JSON and the public-account disclosure before confirming.
5. Let the tool build and validate an isolated two-file change and open the pull request.

If a publication attempt is cancelled or fails, use
`litb publish-submission --candidate .local/leaderboard-submissions/<submission-id>.json` to retry
the already-saved candidate without rerunning the benchmark.

The manual `litb prepare-submission` → copy → rebuild → validate → PR process remains available in
[submitting a benchmark](docs/submitting-benchmarks.md). Automated benchmark PRs may add exactly one
digest-named submission and update the generated leaderboard; do not mix code or documentation into
them. To use the automated review and merge lane, a manual PR must use the exact branch name
`litb/submission-<submission-id>`, with the digest matching the added filename and content ID.
That namespace is reserved for exact generated submissions; a branch with that name fails the
trusted boundary if it contains a general, mixed, or otherwise non-submission change.

For an exact benchmark-only PR, trusted base code revalidates the file modes, schema, canonical
digest, duplicate status, and deterministic leaderboard before posting one fixed GitHub Actions audit
marker bound to the full base and head SHAs. After the marker job succeeds, it directly invokes a
local reusable workflow from the same trusted caller commit. That workflow independently verifies
the exact live, unedited marker and revalidates the complete pull request before it may arm GitHub's
protected squash auto-merge and add an exact-head approval from the configured reviewer account.
The required `Trusted benchmark boundary` context is emitted by a final aggregator and remains
pending until that downstream automation succeeds. The marker is audit evidence, not authorization
by itself.

Codex and CodeRabbit review is best-effort and advisory; automation does not wait for either service.
A clean, absent, failed, skipped, or rate-limited response is not a merge signal. A review thread or
changes request visible to the final revalidation still fails closed, as do stale data and general
code changes. Comments written with the repository `GITHUB_TOKEN` do not start a downstream
`issue_comment` workflow, so a clean Codex comment is not used as the gate.

Per-run automation checks public protected status, the GitHub-Actions-bound required-check summary,
and native review decision. Administration-only protection settings remain repository-operator
prerequisites and are not inferred from contributor-controlled events. The caller maps repository
secret `ERNEST_REVIEW_TOKEN` explicitly to the reusable workflow's `reviewer_token`; inherited
secrets are forbidden, and only the final mutation step binds that credential.

The submission JSON has no contributor field, but your GitHub account and pull request are public.
Exact hardware and performance details can also make a setup recognizable. Do not submit a file you
have not read in full. The digest and deterministic build establish content integrity and schema
conformance, not provenance or attestation that the self-reported benchmark run occurred.

## Pull requests

Explain the user story and requirement IDs affected, the validation commands run, any schema impact,
and whether the public data boundary changes. Do not bypass the local hook. If a scanner blocks a
legitimate example, rewrite the example; do not add a realistic secret to an allowlist.
