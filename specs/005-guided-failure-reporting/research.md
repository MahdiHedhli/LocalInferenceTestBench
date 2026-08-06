# Research: Guided benchmark failure reporting

## Decision: use GitHub's prefilled issue URL

GitHub documents `title` and `body` query parameters for opening a pre-populated issue composer:
[Creating an issue from a URL query](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-an-issue#creating-an-issue-from-a-url-query).

The implementation uses the fixed canonical repository URL and those two parameters only. It does
not use `labels`, repository overrides, templates, the Issues API, a PAT, or GitHub CLI. This keeps
GitHub's own Submit button as the only public creation action.

## Decision: consent precedes browser navigation

A prefilled URL is not local once opened: its query is sent to GitHub and can enter browser,
network, proxy, and service logs before an issue is submitted. The CLI therefore previews the exact
draft and discloses that transmission before accepting one ASCII `y` or `Y` after surrounding ASCII
whitespace is trimmed. Enter, EOF, any other value, non-TTY execution, and the explicit `none` mode
perform no browser call.

## Decision: diagnose execution, not model quality

The prompt is limited to categories that may reveal a runner/runtime compatibility problem.
Semantic failure, exact-format failure, refusal, reasoning-only output, context/output limits,
not-applicable cases, and noisy measurement validity are benchmark evidence rather than harness
failures. Authentication, rate limiting, configuration, endpoint safety, and publication problems
have existing local remediation and are also excluded.

`request_rejected` remains eligible because otherwise-valid local runtimes commonly differ in their
OpenAI-compatible request support; the issue text describes it as a compatibility signal, not proof
of a project defect.

## Decision: structured codes, never error parsing

`ClientError.category` already supplies bounded transport categories. Preflight wrapping adds a
structured diagnostic to `RunnerError`; the CLI never parses its message. Unexpected exceptions are
reduced at the narrow runner boundary to one fixed internal category. No exception object or cause
is accepted by the draft renderer.

## Decision: useful but coarse environment context

OS, Python, and architecture are reduced to small enums. Exact CPU/GPU/RAM/OS-build inventory is
excluded. A hardware class and runtime triple are used only when the operator's existing public
descriptor passes its full owner-only, ignored, descriptor-grade validation. Missing or invalid
metadata becomes `unknown` without affecting the original run failure.

## Alternatives rejected

- **Create issues through the API or `gh`**: requires credentials and creates public state without
  GitHub's final human confirmation.
- **Attach logs or exception messages**: transport libraries and local tools can embed endpoints,
  headers, paths, prompts, or model content.
- **Save a draft JSON file**: creates unnecessary local retention and another permissions/lifecycle
  boundary.
- **Use a free-text issue note**: creates an injection and privacy surface before the user reaches
  GitHub's editor.
- **Prompt on every failed score**: conflates model behavior with a test-bench execution defect and
  would flood maintainers with low-value reports.
