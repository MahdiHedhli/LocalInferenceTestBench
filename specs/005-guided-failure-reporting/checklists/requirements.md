# Requirements checklist: Guided benchmark failure reporting

- [x] User stories are independently testable.
- [x] Eligible and ineligible failure boundaries are explicit.
- [x] The complete draft schema and value enums are closed.
- [x] Prohibited data includes content, credentials, endpoints, paths, inventory, IDs, and time.
- [x] Browser navigation is correctly described as immediate transmission to GitHub.
- [x] GitHub Submit remains the separate public confirmation.
- [x] Non-TTY, decline, EOF, and disabled behavior require zero browser calls.
- [x] Browser failure cannot replace the benchmark result or exit status.
- [x] No PAT, `gh`, Issues API, shell, local persistence, dependency, or auto-submit is permitted.
- [x] Benchmark, submission, leaderboard, Pages, and trusted-workflow scope is unchanged.
