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
2. Enable native pull-request auto-merge for the repository.
3. Keep `main` strict and require the three platform tests, `Publication boundary`, and
   `Trusted benchmark boundary`, all bound to the GitHub Actions App.
4. Keep one approving review, stale-review dismissal, last-push approval, conversation resolution,
   linear history, admin enforcement, and force-push/deletion prohibitions enabled.

The workflow proves the public app-bound required-check summary and native review decision on every
run. GitHub does not expose all settings in step 4 to its read-only identities, so an operator must
verify them before enabling automation and again after any repository-protection change.

## End-to-end behavior

Open a genuine generated benchmark PR from a current base. The trusted boundary validates content
before posting one fixed Codex/CodeRabbit request. A clean same-head Codex response causes the trusted
workflow to revalidate, arm protected squash auto-merge, and add the exact-head reviewer approval.
Findings, stale data, unresolved threads, missing protection, and non-benchmark changes remain open.

For a manually prepared PR, create the branch as `litb/submission-<submission-id>`; the digest must
match the sole added JSON filename and canonical content ID. Unknown mergeability receives bounded
retries. An established `unstable` state may enter native auto-merge, but it never counts as a passed
required check and never bypasses GitHub's merge decision.

If a prior workflow run approved the exact head but did not leave auto-merge armed, a later eligible
event may re-arm it only after the full authorization repeats. A dismissed approval, a later change
request, or an approval for another head is never reused.

Disable native auto-merge and remove the reviewer secret to stop mutation without changing the
append-only or publication checks.
