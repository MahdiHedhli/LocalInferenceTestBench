# Tasks: Trusted submission auto-merge

- [x] T001 Specify trusted-marker, reusable-workflow, credential, and auto-merge contracts.
- [x] T002 Add required-benchmark classification and regression tests.
- [x] T003 Add strict GitHub Actions/App marker parser and adversarial fixtures.
- [x] T004 Add the idempotent audit marker and direct local reusable-workflow call after trusted
  content validation.
- [x] T005 Add same-head revalidation, bounded mergeability retry, protected squash auto-merge,
  latest-decisive reviewer approval, and fail-closed partial-run retry handling.
- [x] T006 Add workflow contract tests for pwn-request, local-caller provenance, explicit secret
  mapping, race, and bypass boundaries.
- [x] T007 Update contributor, submission, and security documentation.
- [x] T008 After this base-controlled workflow revision reached `main`, complete the hosted
  end-to-end validation of the direct reusable-workflow path on benchmark submission PR #15 and
  confirm repository auto-merge through authoritative repository validation.
  - Trusted workflow run: `31072182271`
  - Protected squash merge: `ffd8d38da9e702677314647773ac71a70a1b7e0b`
  - Pages run: `31072226059`
  - Public Safety run: `31072226043`
  - The reviewer identity authoritatively revalidated repository `allow_auto_merge: true`
    immediately before the protected mutation; no administrative bypass was used.
