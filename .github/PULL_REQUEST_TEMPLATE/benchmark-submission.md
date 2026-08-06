## Benchmark submission

Submission ID:

Model:

Submission schema: `1.1`

Suite version: `1.0`

Automated-lane branch: `litb/submission-<submission-id>`

## Contributor checks

- [ ] I created this schema `1.1` file with `litb prepare-submission` from a valid registered-suite
  report and owner-only categorical measurement evidence. Open schema `1.0` submissions must be
  regenerated; accepted historical files must not be rewritten.
- [ ] I read the entire submitted JSON file.
- [ ] The hardware descriptor lists the exact devices used for inference and no unused inventory.
- [ ] The record contains no hostname, account, network value, serial number, inventory ID, device
  UUID, local service label, or free-form note.
- [ ] I understand that exact hardware and performance can make a setup recognizable.
- [ ] I understand that this result is self-reported and unverified; its digest establishes content
  integrity, not provenance or attestation that the run occurred.
- [ ] I understand that this pull request and my GitHub account are public.
- [ ] I verified that `measurement_period` is month-only, measurement conditions contain no raw host
  values, and execution validity was not treated as proof of clean conditions.
- [ ] I regenerated `site/data/leaderboard.json` without editing it by hand.
- [ ] `python3 scripts/build_leaderboard.py --check` passes.
- [ ] `python3 -m unittest discover -s tests -v` passes.
- [ ] `./scripts/public-check --full-tree --strict` passes.

## Review notes

Describe only contract or validation details. Do not paste raw model output, local paths, endpoint
values, scanner matches, or other environment information.

Exact benchmark-only changes on the deterministic digest branch may enter the base-controlled review
and protected auto-merge lane. Findings, unresolved threads, stale data, and failed checks leave the
pull request open. The fixed GitHub Actions marker is audit evidence, not authorization by itself;
the local reusable workflow independently revalidates the exact head before any protected mutation.
Codex and CodeRabbit feedback is best-effort advisory, and automation does not wait for it.
