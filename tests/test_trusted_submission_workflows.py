from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted(
    path
    for pattern in ("*.yml", "*.yaml")
    for path in (ROOT / ".github/workflows").glob(pattern)
)


class TrustedSubmissionWorkflowContractTests(unittest.TestCase):
    def test_boundary_requests_both_reviewers_only_after_trusted_classification(self) -> None:
        workflow = (ROOT / ".github/workflows/trusted-benchmark-boundary.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("pull_request_target:", workflow)
        self.assertIn("issues: write", workflow)
        self.assertIn("change boundary passed: benchmark-only", workflow)
        self.assertIn(
            "python3 scripts/trusted_submission_automation.py review-request",
            workflow,
        )
        self.assertIn("--body-output", workflow)
        self.assertNotIn("@codex review", workflow)
        self.assertNotIn("@coderabbitai review", workflow)
        self.assertNotIn("litb-review-request:", workflow)
        self.assertNotIn('"github-actions[bot]"', workflow)
        self.assertIn("needs: boundary", workflow)
        self.assertIn("needs.boundary.outputs.classification == 'benchmark-only'", workflow)
        self.assertIn('classification="benchmark-manual"', workflow)
        self.assertIn("HEAD_REF: ${{ github.event.pull_request.head.ref }}", workflow)
        self.assertIn('^litb/submission-([0-9a-f]{64})$', workflow)
        self.assertIn("--expected-submission-id", workflow)
        self.assertLess(
            workflow.index("--expected-submission-id"),
            workflow.index(
                "python3 scripts/trusted_submission_automation.py review-request"
            ),
        )
        self.assertEqual(workflow.count("persist-credentials: false"), 2)
        self.assertEqual(workflow.count("contents: read"), 2)
        self.assertNotIn("github.event.pull_request.body", workflow)
        self.assertNotIn("github.event.comment.body", workflow)
        self.assertRegex(workflow, r"actions/checkout@[0-9a-f]{40}")

    def test_auto_merge_runs_from_default_branch_and_never_executes_head_code(self) -> None:
        workflow = (ROOT / ".github/workflows/trusted-benchmark-auto-merge.yml").read_text(
            encoding="utf-8"
        )
        review_threads_query = (
            ROOT / "scripts/queries/review_threads.graphql"
        ).read_text(encoding="utf-8")
        auto_merge_query = (
            ROOT / "scripts/queries/auto_merge_state.graphql"
        ).read_text(encoding="utf-8")
        trusted_contract = "\n".join((workflow, review_threads_query, auto_merge_query))

        self.assertIn("issue_comment:", workflow)
        self.assertRegex(workflow, r"types:\s*\n\s*- created")
        self.assertIn("chatgpt-codex-connector[bot]", workflow)
        self.assertIn("github.event.comment.user.id == 199175422", workflow)
        self.assertIn("github.event.comment.performed_via_github_app.id == 1144995", workflow)
        self.assertIn("scripts/trusted_submission_automation.py", workflow)
        self.assertIn('git show "${BASE_SHA}:scripts/validate_benchmark_change.py"', workflow)
        self.assertIn("--require-benchmark", workflow)
        self.assertIn("--check-content", workflow)
        self.assertIn("scripts/queries/review_threads.graphql", workflow)
        self.assertIn("scripts/queries/auto_merge_state.graphql", workflow)
        self.assertIn("reviewThreads", review_threads_query)
        self.assertIn("id", review_threads_query)
        self.assertIn("isResolved", review_threads_query)
        self.assertNotIn("nodes{isResolved}", trusted_contract)
        self.assertIn("enablePullRequestAutoMerge", workflow)
        self.assertIn("expectedHeadOid", workflow)
        self.assertIn("mergeMethod:SQUASH", workflow)
        self.assertIn("commitOID", workflow)
        self.assertIn("reviewDecision", auto_merge_query)
        self.assertIn("commitHeadline", trusted_contract)
        self.assertIn("commitBody", trusted_contract)
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
        helper = (ROOT / "scripts/fetch_mergeable_pull.sh").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("fetch_mergeable_pull()", workflow)
        self.assertEqual(workflow.count("bash scripts/fetch_mergeable_pull.sh"), 2)
        self.assertEqual(workflow.count('bash "${mergeable_helper}"'), 3)
        self.assertIn("scripts/fetch_mergeable_pull.sh", workflow)
        self.assertEqual(helper.count("for attempt in 1 2 3 4 5; do"), 1)
        for state in ("blocked", "clean", "unstable"):
            self.assertEqual(helper.count(f'.mergeable_state == "{state}"'), 1)
        self.assertNotIn('.mergeable_state == "dirty"', helper)
        self.assertNotIn('.mergeable_state == "behind"', helper)
        self.assertIn("^[1-9][0-9]*$", helper)
        self.assertIn("sleep 2", helper)

    def test_reused_graphql_queries_are_loaded_from_trusted_base_files(self) -> None:
        workflow = (ROOT / ".github/workflows/trusted-benchmark-auto-merge.yml").read_text(
            encoding="utf-8"
        )
        review_threads_query = (
            ROOT / "scripts/queries/review_threads.graphql"
        ).read_text(encoding="utf-8")
        auto_merge_query = (
            ROOT / "scripts/queries/auto_merge_state.graphql"
        ).read_text(encoding="utf-8")

        self.assertNotIn("reviewThreads(first:", workflow)
        self.assertEqual(
            workflow.count(
                '-F query=@"${GITHUB_WORKSPACE}/scripts/queries/review_threads.graphql"'
            ),
            1,
        )
        self.assertEqual(workflow.count('-F query=@"${review_threads_query}"'), 3)
        self.assertEqual(workflow.count('-F query=@"${auto_merge_query}"'), 3)
        self.assertIn("scripts/queries/review_threads.graphql", workflow)
        self.assertIn("scripts/queries/auto_merge_state.graphql", workflow)
        self.assertIn("?ref=${BASE_SHA}", workflow)
        self.assertNotIn("?ref=${HEAD_SHA}", workflow)
        self.assertLess(
            workflow.index('git checkout --detach "${BASE_SHA}"'),
            workflow.index(
                '-F query=@"${GITHUB_WORKSPACE}/scripts/queries/review_threads.graphql"'
            ),
        )
        self.assertIn("$endCursor: String", review_threads_query)
        self.assertIn("nodes", review_threads_query)
        self.assertIn("id", review_threads_query)
        self.assertIn("isResolved", review_threads_query)
        self.assertIn("totalCount", review_threads_query)
        self.assertIn("hasNextPage", review_threads_query)
        self.assertIn("endCursor", review_threads_query)
        self.assertEqual(auto_merge_query.count("autoMergeRequest"), 1)
        self.assertIn("reviewDecision", auto_merge_query)

    def test_live_default_branch_must_still_match_before_each_mutation(self) -> None:
        workflow = (ROOT / ".github/workflows/trusted-benchmark-auto-merge.yml").read_text(
            encoding="utf-8"
        )

        identity = workflow.index('python3 "${helper}" identity')
        auto_merge_check = workflow.index(
            'validate_live_base "${RUNNER_TEMP}/base-before-auto-merge.json"'
        )
        auto_merge_mutation = workflow.index("enablePullRequestAutoMerge")
        approval_check = workflow.index(
            'validate_live_base "${RUNNER_TEMP}/base-before-approval.json"'
        )
        approval_mutation = workflow.index("addPullRequestReview")

        self.assertEqual(workflow.count("validate_live_base()"), 1)
        self.assertEqual(
            workflow.count('validate_live_base "${RUNNER_TEMP}/base-before-'), 2
        )
        self.assertIn("repos/MahdiHedhli/LocalInferenceTestBench/branches/main", workflow)
        self.assertIn(".commit.sha | strings", workflow)
        self.assertIn('test "${live_base}" = "${BASE_SHA}"', workflow)
        self.assertLess(identity, auto_merge_check)
        self.assertLess(auto_merge_check, auto_merge_mutation)
        self.assertLess(auto_merge_mutation, approval_check)
        self.assertLess(approval_check, approval_mutation)

    def test_reviewer_secret_is_confined_to_the_final_mutation_step(self) -> None:
        workflow = (ROOT / ".github/workflows/trusted-benchmark-auto-merge.yml").read_text(
            encoding="utf-8"
        )

        secret_reference = "secrets.ERNEST_REVIEW_TOKEN"
        self.assertEqual(workflow.count(secret_reference), 1)
        self.assertLess(workflow.index("Revalidate without reviewer credential"), workflow.index(secret_reference))
        self.assertLess(workflow.index("review_threads.graphql"), workflow.index(secret_reference))
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
        self.assertTrue(WORKFLOWS)
        for path in WORKFLOWS:
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
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            for action in re.findall(r"(?m)^\s*uses:\s*([^\s#]+)", text):
                with self.subTest(workflow=path.name, action=action):
                    self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
