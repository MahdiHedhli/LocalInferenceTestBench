# Security policy

## Supported versions

Security fixes are applied to the latest release and the default branch.

## Reporting a vulnerability

Use GitHub private vulnerability reporting from this repository's Security tab. Do not open a public
issue containing a credential, private identifier, exploitable target, or scanner match. Include the
smallest reproduction necessary and replace environment-specific values with documented placeholders.

If you believe a secret was committed, rotate or revoke it before attempting history cleanup. Scanner
output and remediation discussion must identify the category and affected file without repeating the
secret value.

## Verify hosted protections

Before the first push, confirm in the hosting provider's repository security settings or API that
secret scanning is enabled and that push protection blocks recognized secrets. Recheck after any
visibility transfer or security-plan change. Record only the enabled/disabled states in release
evidence; do not copy repository, account, or scanner identifiers into reusable fixtures.

On GitHub, both `security_and_analysis.secret_scanning.status` and
`security_and_analysis.secret_scanning_push_protection.status` in the repository API response should
be `enabled`. Treat an unavailable control as a release blocker until the maintainer explicitly
documents an equivalent host-side protection.

## Scope

Reports about endpoint validation, secret/identifier scanning bypasses, unsafe persistence of model
content, unintended tool execution, generated-code execution, leaderboard contract bypasses, or
unsafe Pages rendering are in scope. The behavior of a model under test and vulnerabilities in
third-party inference runtimes should be reported to their respective maintainers unless this project
creates or amplifies the issue.
