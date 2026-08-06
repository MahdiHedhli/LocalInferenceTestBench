from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TrustedSubmissionWorkflowContractTests(unittest.TestCase):
    def test_boundary_requests_both_reviewers_only_after_trusted_classification(self) -> None:
        workflow = (ROOT / ".github/workflows/trusted-benchmark-boundary.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("pull_request_target:", workflow)
        self.assertIn("issues: write", workflow)
        self.assertIn("change boundary passed: benchmark-only", workflow)
        self.assertIn("@codex review", workflow)
        self.assertIn("@coderabbitai review", workflow)
        self.assertIn("litb-review-request:", workflow)
        self.assertIn("needs: boundary", workflow)
        self.assertIn("needs.boundary.outputs.classification == 'benchmark-only'", workflow)
        self.assertIn('classification="benchmark-manual"', workflow)
        self.assertIn("HEAD_REF: ${{ github.event.pull_request.head.ref }}", workflow)
        self.assertIn('^litb/submission-([0-9a-f]{64})$', workflow)
        self.assertIn("--expected-submission-id", workflow)
        self.assertLess(workflow.index("--expected-submission-id"), workflow.index("@codex review"))
        self.assertIn("persist-credentials: false", workflow)
        self.assertNotIn("github.event.pull_request.body", workflow)
        self.assertNotIn("github.event.comment.body", workflow)
        self.assertRegex(workflow, r"actions/checkout@[0-9a-f]{40}")

    def test_auto_merge_runs_from_default_branch_and_never_executes_head_code(self) -> None:
        workflow = (ROOT / ".github/workflows/trusted-benchmark-auto-merge.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("issue_comment:", workflow)
        self.assertRegex(workflow, r"types:\s*\n\s*- created")
        self.assertIn("chatgpt-codex-connector[bot]", workflow)
        self.assertIn("github.event.comment.user.id == 199175422", workflow)
        self.assertIn("github.event.comment.performed_via_github_app.id == 1144995", workflow)
        self.assertIn("scripts/trusted_submission_automation.py", workflow)
        self.assertIn('git show "${BASE_SHA}:scripts/validate_benchmark_change.py"', workflow)
        self.assertIn("--require-benchmark", workflow)
        self.assertIn("--check-content", workflow)
        self.assertIn("reviewThreads", workflow)
        self.assertNotIn("nodes{isResolved}", workflow)
        self.assertEqual(workflow.count("nodes{id isResolved}"), 4)
        self.assertIn("enablePullRequestAutoMerge", workflow)
        self.assertIn("expectedHeadOid", workflow)
        self.assertIn("mergeMethod:SQUASH", workflow)
        self.assertIn("commitOID", workflow)
        self.assertIn("reviewDecision", workflow)
        self.assertIn("commitHeadline", workflow)
        self.assertIn("commitBody", workflow)
        self.assertIn("data: add benchmark submission", workflow)
        self.assertIn('grep -Fqx "review_decision=APPROVED"', workflow)
        self.assertIn('grep -Fqx "review_decision=REVIEW_REQUIRED"', workflow)
        self.assertIn('pull-request-after-arm.json', workflow)
        self.assertIn("trusted benchmark auto-merge completed", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertRegex(workflow, r"actions/checkout@[0-9a-f]{40}")
        self.assertNotIn("github.event.comment.body", workflow)
        self.assertNotIn("pull_request_target:", workflow)
        self.assertNotIn("--admin", workflow)
        self.assertNotIn("mergePullRequest", workflow)
        self.assertNotIn("gh pr merge", workflow)
        self.assertNotRegex(workflow, r"(?m)^\s*git push\b")
        self.assertNotIn("pull/${PR_NUMBER}/merge", workflow)
        self.assertNotIn('git checkout --detach "${HEAD_SHA}"', workflow)

    def test_pull_request_mergeability_is_retried_with_a_closed_allowlist(self) -> None:
        workflow = (ROOT / ".github/workflows/trusted-benchmark-auto-merge.yml").read_text(
            encoding="utf-8"
        )

        self.assertEqual(workflow.count("fetch_mergeable_pull()"), 4)
        self.assertEqual(workflow.count("fetch_mergeable_pull \"${RUNNER_TEMP}"), 5)
        self.assertEqual(workflow.count("for attempt in 1 2 3 4 5; do"), 4)
        for state in ("blocked", "clean", "unstable"):
            self.assertEqual(workflow.count(f'.mergeable_state == "{state}"'), 4)
        self.assertNotIn('.mergeable_state == "dirty"', workflow)
        self.assertNotIn('.mergeable_state == "behind"', workflow)
        self.assertIn("sleep 2", workflow)

    def test_reviewer_secret_is_confined_to_the_final_mutation_step(self) -> None:
        workflow = (ROOT / ".github/workflows/trusted-benchmark-auto-merge.yml").read_text(
            encoding="utf-8"
        )

        secret_reference = "secrets.ERNEST_REVIEW_TOKEN"
        self.assertEqual(workflow.count(secret_reference), 1)
        self.assertLess(workflow.index("Revalidate without reviewer credential"), workflow.index(secret_reference))
        self.assertLess(workflow.index("reviewThreads"), workflow.index(secret_reference))
        self.assertLess(workflow.index("--require-benchmark"), workflow.index(secret_reference))
        prefix, suffix = workflow.split(secret_reference, 1)
        self.assertNotIn("ERNEST_REVIEW_TOKEN", prefix)
        self.assertNotIn("ERNEST_REVIEW_TOKEN", suffix)

    def test_untrusted_pull_request_metadata_never_becomes_the_squash_message(self) -> None:
        workflow = (ROOT / ".github/workflows/trusted-benchmark-auto-merge.yml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("github.event.issue.title", workflow)
        self.assertNotIn("github.event.issue.body", workflow)
        self.assertNotIn("github.event.pull_request.title", workflow)
        self.assertNotIn("github.event.pull_request.body", workflow)
        self.assertIn(
            'headline="data: add benchmark submission ${SUBMISSION_ID:0:12}"',
            workflow,
        )
        self.assertIn("Schema-validated self-reported benchmark record; run unverified.", workflow)

    def test_event_expressions_are_never_interpolated_inside_shell_programs(self) -> None:
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            lines = path.read_text(encoding="utf-8").splitlines()
            run_indent: int | None = None
            for line_number, line in enumerate(lines, 1):
                stripped = line.lstrip()
                indentation = len(line) - len(stripped)
                if run_indent is not None and stripped and indentation <= run_indent:
                    run_indent = None
                if stripped.startswith("run:"):
                    run_indent = indentation
                if run_indent is not None:
                    with self.subTest(workflow=path.name, line=line_number):
                        self.assertNotIn("${{", line)

    def test_all_workflow_actions_are_sha_pinned(self) -> None:
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            text = path.read_text(encoding="utf-8")
            for action in re.findall(r"(?m)^\s*uses:\s*([^\s#]+)", text):
                with self.subTest(workflow=path.name, action=action):
                    self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
