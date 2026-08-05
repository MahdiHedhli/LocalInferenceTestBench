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
   enter the exact hardware used for inference plus the serving runtime.
3. Run `litb prepare-submission` and review the complete minimized JSON file.
4. Copy that file to `site/data/submissions/<submission_id>.json`.
5. Run `python3 scripts/build_leaderboard.py` and commit the regenerated dataset.
6. Run the unit suite and `./scripts/public-check --full-tree --strict`.
7. Open the pull request with the benchmark submission template.

The submission JSON has no contributor field, but your GitHub account and pull request are public.
Exact hardware and performance details can also make a setup recognizable. Do not submit a file you
have not read in full.

## Pull requests

Explain the user story and requirement IDs affected, the validation commands run, any schema impact,
and whether the public data boundary changes. Do not bypass the local hook. If a scanner blocks a
legitimate example, rewrite the example; do not add a realistic secret to an allowlist.
