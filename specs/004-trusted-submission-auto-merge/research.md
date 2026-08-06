# Research: Trusted submission auto-merge

## Review signals

Codex clean reviews arrive as top-level issue comments from immutable user ID `199175422` through
GitHub App ID `1144995`. The human-readable commit marker contains only ten hexadecimal characters,
so it is never the full authorization. A base-controlled request comment records the complete base
and head SHAs before the clean response.

CodeRabbit may report a successful commit status while its description says review was rate-limited.
That status is availability information only. Neither CodeRabbit nor Codex replaces deterministic
validation or branch protection.

## Merge ordering

A fresh authorization requires `REVIEW_REQUIRED` and no existing exact-head Ernest approval before
native auto-merge is armed. This keeps the request blocked while GitHub records the full-head
auto-merge guard and fixed squash metadata. The exact-head approval is added last.

A retry after a partial workflow run is different: a latest decisive Ernest approval for the exact
current head may already exist while the auto-merge request is missing. After the complete content,
identity, comment, thread, review, and head revalidation repeats, the workflow may re-arm native
auto-merge without manufacturing another approval. A later dismissal or change request, or an
approval tied to any other commit, invalidates reuse. GitHub then enforces every required check and
configured repository protection in both paths.

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

The reviewer credential is a repository secret exposed only to the final mutation step. The step
pins its immutable account ID before any write. A dedicated short-lived GitHub App token would be a
future reduction in credential blast radius; it is not required for this feature.
