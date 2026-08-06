# Research: Trusted submission auto-merge

## Trusted audit marker and direct call

The base-controlled boundary posts a fixed comment only after it classifies and validates an exact
benchmark-only change. GitHub records that comment under GitHub Actions user ID `41898282` and
GitHub App ID `15368`. Its canonical body binds the full base and head SHAs. The downstream workflow
fetches the exact comment ID live and requires matching actor/App IDs and equal creation/update
timestamps, so an edited or substituted comment fails closed.

Those user/App IDs identify GitHub Actions, not one unique workflow. Another repository workflow
with pull-request comment permission could produce the same actor identity. The marker therefore
derives its limited audit value from the successful trusted-job dependency and exact live binding;
it can never replace downstream revalidation.

The marker is audit evidence that the trusted classification path completed; it is not sufficient
authorization. The successful marker job directly invokes a local reusable workflow resolved from
the same trusted caller commit and supplies the exact PR number, full base SHA, full head SHA, and
comment ID. The called workflow independently retrieves and verifies every live authorization input
before mutation.

GitHub deliberately prevents most events created with a repository `GITHUB_TOKEN` from creating a
new workflow run. Consequently, the marker's comment event does not trigger an `issue_comment`
workflow. A clean Codex comment is therefore removed as an automation gate; using a direct local
reusable-workflow call preserves a base-controlled chain without a broad maintainer PAT or event-loop
workaround. See GitHub's
[GITHUB_TOKEN event behavior](https://docs.github.com/en/actions/concepts/security/github_token).

Codex and CodeRabbit remain best-effort advisory reviewers. Rate limiting, absence, connector
failure, or a clean response is availability/review information only. Automation does not wait for
either service. A review thread or changes request that arrives before final authorization is still
read as live GitHub state and fails closed. Neither reviewer replaces deterministic validation or
branch protection.

## Merge ordering

A fresh authorization requires `REVIEW_REQUIRED` and no existing exact-head Ernest approval before
native auto-merge is armed. This keeps the request blocked while GitHub records the full-head
auto-merge guard and fixed squash metadata. The exact-head approval is added last.

A retry after a partial workflow run is different: a latest decisive Ernest approval for the exact
current head may already exist while the auto-merge request is missing. After the complete content,
identity, comment, thread, review, and head revalidation repeats, the workflow may re-arm native
auto-merge without manufacturing another approval. The final required `Trusted benchmark boundary`
context is still pending during that retry, so the PR retains a native requirement and can accept a
new auto-merge request. A later dismissal or change request, or an approval tied to any other commit,
invalidates reuse. GitHub then enforces every required check and configured repository protection in
both paths.

The final required boundary is also the recovery guard for the fresh path. Native auto-merge is armed
before Ernest approves the exact head, but the required boundary does not turn green until the entire
called workflow finishes. A transport or parser failure after arming therefore cannot become
mergeable merely because another reviewer later approves the PR.

## Mergeability and retries

GitHub may briefly return unknown mergeability while computing a PR's graph state. That is an
availability condition, not a rejection or an authorization, so the workflow retries it for a
bounded interval and then fails closed. Once `mergeable=true`, `blocked`, `clean`, and `unstable`
may enter the remaining guarded authorization checks. In particular, `unstable` does not mean a
check passed: the workflow still requires the named app-bound checks to exist, and GitHub still
withholds the merge until its configured requirements pass.

The automated lane also binds the live branch `litb/submission-<digest>` to the sole added submission
filename and content ID. This is automatic for `litb`; manual publishers must create that exact branch
name themselves.

## Permission boundary

The public branch endpoint exposes protected status and app-bound required checks to read-only jobs.
Administration-only protection details are not available to `GITHUB_TOKEN` or the non-admin reviewer
account. The workflow therefore validates the public protected flag, app-bound required-check
summary and enforcement level, plus native review decision. It does not claim per-run proof of
stale-review dismissal, last-push approval, conversation resolution, linear history, all admin
settings, or force-push/deletion prohibitions. Those remain explicit operator prerequisites and must
be rechecked after repository-setting changes. GitHub enforces the configured controls when native
auto-merge evaluates the PR.

The trusted caller maps repository secret `ERNEST_REVIEW_TOKEN` explicitly to the local reusable
workflow's `reviewer_token`; `secrets: inherit` is prohibited. The credential is bound only to the
final mutation step after all public-token checks pass, and the step pins its immutable account ID
before any write. Boundary and marker jobs never receive it. A dedicated short-lived GitHub App
token would be a future reduction in credential blast radius; it is not required for this feature.

## Integrity and provenance

Canonical digest and deterministic rebuild checks establish that accepted public bytes satisfy the
schema and have not changed relative to their content ID. They cannot establish that a benchmark was
run or that self-reported performance is truthful. The marker, advisory reviews, automated Ernest
approval, and native auto-merge are publication-policy evidence, not benchmark provenance or
attestation.
