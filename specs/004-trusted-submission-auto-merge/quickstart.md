# Quickstart: Trusted submission auto-merge

## Local verification

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_leaderboard.py --check
./scripts/public-check --full-tree --strict
```

## Repository setup after merge

1. Add the dedicated reviewer credential as the Actions secret `ERNEST_REVIEW_TOKEN`, using the
   narrowest repository scope the credential type supports. Do not paste it into an issue, pull
   request, workflow input, command argument, or tracked file.
2. Keep the repository's default workflow permission read-only and leave “Allow GitHub Actions to
   create and approve pull requests” disabled (`can_approve_pull_request_reviews: false`).
3. Enable native pull-request auto-merge for the repository.
4. Keep `main` strict and require the three platform tests, `Publication boundary`, and
   `Trusted benchmark boundary`, all bound to the GitHub Actions App.
5. Keep one approving review, stale-review dismissal, last-push approval, conversation resolution,
   linear history, admin enforcement, and force-push/deletion prohibitions enabled.

The workflow proves the public app-bound required-check summary and native review decision on every
run. GitHub does not expose all settings in steps 2, 3, and 5 to its read-only identities, so an
operator must verify them before enabling automation and again after any repository-protection
change. The final reviewer-credential step independently requires `allow_auto_merge: true`
immediately before each possible mutation. If that setting is disabled or unconfirmable, the final
required boundary remains failed.

The base-controlled caller must map repository secret `ERNEST_REVIEW_TOKEN` explicitly to the local
reusable workflow's `reviewer_token`; do not use `secrets: inherit`. Only the reusable workflow's
final mutation step may bind the secret.

## End-to-end behavior

Open a genuine generated benchmark PR from a current base. The trusted boundary validates content
before posting one fixed Actions/App audit marker. When that job succeeds, it directly calls the
local reusable workflow from the same trusted commit with the exact PR number, full base and head
SHAs, and marker comment ID. The reusable workflow verifies the exact live, unedited marker and then
independently revalidates content and live repository state before it may arm protected squash
auto-merge and add the exact-head reviewer approval. The marker is audit evidence, not authorization
on its own.

Codex and CodeRabbit may provide best-effort advisory review, but automation neither waits for nor
interprets their response as authorization. Repository-`GITHUB_TOKEN` comments do not start an
`issue_comment` workflow, so a clean Codex reply is not the gate. A review thread or changes request
visible before final authorization still fails closed, as do stale data, missing protection, and
non-benchmark changes.

For a manually prepared PR, create the branch as `litb/submission-<submission-id>`; the digest must
match the sole added JSON filename and canonical content ID. Unknown mergeability receives bounded
retries. An established `unstable` state may enter native auto-merge, but it never counts as a passed
required check and never bypasses GitHub's merge decision. That branch namespace is reserved: a
general, mixed, or otherwise non-submission diff under it fails the trusted boundary.

If a prior workflow run approved the exact head but did not leave auto-merge armed, a later eligible
event may re-arm it only after the full authorization repeats and while a native requirement remains
pending. The final required `Trusted benchmark boundary` aggregator stays pending through this
sequence, preventing an already-clean state and preventing an orphaned approval from merging after a
failed automation attempt. A dismissed approval, a later change request, or an approval for another
head is never reused.

Disable native auto-merge and remove the reviewer secret to stop mutation without changing the
append-only or publication checks.

The deterministic checks establish schema conformance and content integrity. They do not attest
that the self-reported benchmark run occurred.
