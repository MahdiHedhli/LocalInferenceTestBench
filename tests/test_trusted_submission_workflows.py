from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_PATH = ROOT / ".github/workflows/trusted-benchmark-boundary.yml"
AUTO_MERGE_PATH = ROOT / ".github/workflows/trusted-benchmark-auto-merge.yml"
WORKFLOWS = sorted(
    path
    for pattern in ("*.yml", "*.yaml")
    for path in (ROOT / ".github/workflows").glob(pattern)
)


class TrustedSubmissionWorkflowContractTests(unittest.TestCase):
    def test_boundary_calls_local_automation_only_after_validation_and_marker(self) -> None:
        workflow = BOUNDARY_PATH.read_text(encoding="utf-8")

        self.assertIn("pull_request_target:", workflow)
        self.assertIn(
            "concurrency:\n"
            "  group: trusted-benchmark-boundary-"
            "${{ github.repository_id }}-${{ github.event.pull_request.number }}\n"
            "  cancel-in-progress: false",
            workflow,
        )
        self.assertIn("change boundary passed: benchmark-only", workflow)
        self.assertIn('classification="benchmark-manual"', workflow)
        self.assertIn('^litb/submission-([0-9a-f]{64})$', workflow)
        self.assertIn("--expected-submission-id", workflow)
        general_case = workflow[
            workflow.index('"change boundary passed: general")') : workflow.index(
                '*) exit 1 ;;'
            )
        ]
        self.assertIn('if [ -n "${expected_submission_id}" ]; then', general_case)
        self.assertIn("exit 1", general_case)
        self.assertIn('classification="general"', general_case)
        self.assertIn("python3 scripts/trusted_submission_automation.py review-request", workflow)
        self.assertIn("--body-output", workflow)
        self.assertNotIn("@codex review", workflow)
        self.assertNotIn("@coderabbitai review", workflow)
        self.assertNotIn("litb-review-request:", workflow)

        request_job = workflow[
            workflow.index("  request-reviews:") : workflow.index("  trusted-auto-merge:")
        ]
        request_permissions = re.search(
            r"(?m)^    permissions:\n(?P<body>(?:      [^\n]+\n)+)    outputs:",
            request_job,
        )
        self.assertIsNotNone(request_permissions)
        assert request_permissions is not None
        self.assertEqual(
            request_permissions.group("body"),
            "      contents: read\n      pull-requests: write\n",
        )
        self.assertIn("needs: boundary", request_job)
        self.assertIn("needs.boundary.outputs.classification == 'benchmark-only'", request_job)
        self.assertNotIn("issues: write", request_job)
        self.assertIn("marker_comment_id: ${{ steps.marker.outputs.marker_comment_id }}", request_job)
        self.assertIn("litb-comments-final.json", request_job)
        self.assertLess(
            workflow.index("--expected-submission-id"),
            workflow.index("python3 scripts/trusted_submission_automation.py review-request"),
        )

        call_job = workflow[
            workflow.index("  trusted-auto-merge:") : workflow.index(
                "  required-boundary:"
            )
        ]
        reviewer_secret_name = "reviewer_" + "token"
        caller_permissions = re.search(
            r"(?m)^    permissions:\n(?P<body>(?:      [^\n]+\n)+)    uses:",
            call_job,
        )
        self.assertIsNotNone(caller_permissions)
        assert caller_permissions is not None
        self.assertEqual(
            caller_permissions.group("body"),
            "      contents: read\n      issues: read\n      pull-requests: read\n",
        )
        self.assertIn("needs:\n      - boundary\n      - request-reviews", call_job)
        self.assertIn("uses: ./.github/workflows/trusted-benchmark-auto-merge.yml", call_job)
        self.assertIn("pull_request_number: ${{ needs.boundary.outputs.pull_request_number }}", call_job)
        self.assertIn("base_sha: ${{ needs.boundary.outputs.base_sha }}", call_job)
        self.assertIn("head_sha: ${{ needs.boundary.outputs.head_sha }}", call_job)
        self.assertIn("marker_comment_id: ${{ needs.request-reviews.outputs.marker_comment_id }}", call_job)
        self.assertIn(
            reviewer_secret_name + ": ${{ secrets.ERNEST_REVIEW_TOKEN }}",
            call_job,
        )
        self.assertNotIn("secrets: inherit", call_job)
        self.assertNotIn("runs-on:", call_job)
        self.assertNotIn("steps:", call_job)
        self.assertEqual(workflow.count("pull-requests: write"), 1)
        self.assertNotIn("issues: write", workflow)
        self.assertEqual(workflow.count("persist-credentials: false"), 2)

        required_job = workflow[workflow.index("  required-boundary:") :]
        self.assertIn("name: Trusted benchmark boundary", required_job)
        self.assertIn("if: always()", required_job)
        self.assertIn(
            "needs:\n      - boundary\n      - request-reviews\n      - trusted-auto-merge",
            required_job,
        )
        self.assertIn("permissions: {}", required_job)
        self.assertIn('test "${BOUNDARY_RESULT}" = "success"', required_job)
        self.assertIn('test "${REQUEST_RESULT}" = "success"', required_job)
        self.assertIn('test "${AUTOMATION_RESULT}" = "success"', required_job)
        self.assertIn("benchmark-manual|general)", required_job)
        self.assertIn('test "${REQUEST_RESULT}" = "skipped"', required_job)
        self.assertIn('test "${AUTOMATION_RESULT}" = "skipped"', required_job)
        self.assertEqual(
            len(re.findall(r"(?m)^    name: Trusted benchmark boundary$", workflow)),
            1,
        )
        self.assertLess(
            workflow.index("  trusted-auto-merge:"),
            workflow.index("  required-boundary:"),
        )

    def test_reusable_workflow_is_same_commit_only_and_never_executes_head_code(self) -> None:
        workflow = AUTO_MERGE_PATH.read_text(encoding="utf-8")
        reviewer_secret_name = "reviewer_" + "token"
        review_threads_query = (
            ROOT / "scripts/queries/review_threads.graphql"
        ).read_text(encoding="utf-8")
        auto_merge_query = (
            ROOT / "scripts/queries/auto_merge_state.graphql"
        ).read_text(encoding="utf-8")
        trusted_contract = "\n".join((workflow, review_threads_query, auto_merge_query))

        self.assertIn("workflow_call:", workflow)
        self.assertIn("permissions: {}", workflow)
        self.assertNotIn("issue_comment:", workflow)
        self.assertNotIn("pull_request_target:", workflow)
        self.assertNotIn("concurrency:", workflow)
        for name in ("pull_request_number", "base_sha", "head_sha", "marker_comment_id"):
            block = workflow[workflow.index(f"      {name}:") :]
            self.assertIn("required: true", block[:100])
            self.assertIn("type: string", block[:100])
        self.assertIn(
            "      " + reviewer_secret_name + ":\n        required: true",
            workflow,
        )
        self.assertIn("ref: ${{ inputs.base_sha }}", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn('git show "${BASE_SHA}:scripts/validate_benchmark_change.py"', workflow)
        self.assertIn("--require-benchmark", workflow)
        self.assertIn("--check-content", workflow)
        self.assertIn("--base \"${BASE_SHA}\"", workflow)
        self.assertIn("--head \"${HEAD_SHA}\"", workflow)
        self.assertNotIn("--prefix", workflow)
        self.assertIn("issues/comments/${MARKER_COMMENT_ID}", workflow)
        self.assertNotIn("actions/download-artifact", workflow)
        self.assertNotIn("actions/cache", workflow)
        self.assertNotIn('git checkout --detach "${HEAD_SHA}"', workflow)
        self.assertNotIn("?ref=${HEAD_SHA}", workflow)
        read_only_permissions = (
            "    permissions:\n"
            "      contents: read\n"
            "      issues: read\n"
            "      pull-requests: read\n"
        )
        self.assertEqual(workflow.count(read_only_permissions), 2)
        self.assertNotRegex(workflow, r"(?m)^\s+(contents|issues|pull-requests): write$")

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
        self.assertIn("trusted benchmark auto-merge completed", workflow)
        self.assertNotIn("--admin", workflow)
        self.assertNotIn("mergePullRequest", workflow)
        self.assertNotIn("gh pr merge", workflow)
        self.assertNotRegex(workflow, r"(?m)^\s*git push\b")
        self.assertNotIn("pull/${PR_NUMBER}/merge", workflow)

    def test_pull_request_mergeability_is_retried_with_a_closed_allowlist(self) -> None:
        workflow = AUTO_MERGE_PATH.read_text(encoding="utf-8")
        helper = (ROOT / "scripts/fetch_mergeable_pull.sh").read_text(encoding="utf-8")

        self.assertNotIn("fetch_mergeable_pull()", workflow)
        self.assertGreaterEqual(workflow.count("bash scripts/fetch_mergeable_pull.sh"), 2)
        self.assertGreaterEqual(workflow.count('bash "${mergeable_helper}"'), 4)
        self.assertEqual(helper.count("for attempt in 1 2 3 4 5; do"), 1)
        for state in ("blocked", "clean", "unstable"):
            self.assertEqual(helper.count(f'.mergeable_state == "{state}"'), 1)
        self.assertNotIn('.mergeable_state == "dirty"', helper)
        self.assertNotIn('.mergeable_state == "behind"', helper)
        self.assertIn("^[1-9][0-9]*$", helper)
        self.assertIn("sleep 2", helper)

    def test_reused_queries_and_helpers_are_loaded_only_from_the_trusted_base(self) -> None:
        workflow = AUTO_MERGE_PATH.read_text(encoding="utf-8")
        review_threads_query = (
            ROOT / "scripts/queries/review_threads.graphql"
        ).read_text(encoding="utf-8")
        auto_merge_query = (
            ROOT / "scripts/queries/auto_merge_state.graphql"
        ).read_text(encoding="utf-8")

        self.assertNotIn("reviewThreads(first:", workflow)
        self.assertEqual(
            workflow.count('-F query=@"${GITHUB_WORKSPACE}/scripts/queries/review_threads.graphql"'),
            1,
        )
        self.assertGreaterEqual(workflow.count('-F query=@"${review_threads_query}"'), 4)
        self.assertEqual(workflow.count('-F query=@"${auto_merge_query}"'), 3)
        self.assertIn("scripts/trusted_submission_automation.py", workflow)
        self.assertIn("scripts/fetch_mergeable_pull.sh", workflow)
        self.assertIn("scripts/queries/review_threads.graphql", workflow)
        self.assertIn("scripts/queries/auto_merge_state.graphql", workflow)
        self.assertIn("?ref=${BASE_SHA}", workflow)
        self.assertNotIn("?ref=${HEAD_SHA}", workflow)
        self.assertLess(
            workflow.index('git checkout --detach "${BASE_SHA}"'),
            workflow.index('-F query=@"${GITHUB_WORKSPACE}/scripts/queries/review_threads.graphql"'),
        )
        self.assertIn("$endCursor: String", review_threads_query)
        self.assertIn("totalCount", review_threads_query)
        self.assertIn("hasNextPage", review_threads_query)
        self.assertIn("endCursor", review_threads_query)
        self.assertEqual(auto_merge_query.count("autoMergeRequest"), 1)

    def test_full_live_authorization_repeats_immediately_before_each_mutation(self) -> None:
        workflow = AUTO_MERGE_PATH.read_text(encoding="utf-8")

        identity = workflow.index('python3 "${helper}" identity')
        auto_merge_check = workflow.index('validate_live_authorization "before-auto-merge"')
        auto_merge_mutation = workflow.index("enablePullRequestAutoMerge")
        approval_check = workflow.index('validate_live_authorization "before-approval"')
        approval_mutation = workflow.index("addPullRequestReview")

        self.assertEqual(workflow.count("validate_live_authorization()"), 1)
        self.assertEqual(workflow.count("validate_live_authorization \"before-"), 2)
        function = workflow[
            workflow.index("          validate_live_authorization()") : identity
        ]
        self.assertIn("branches/main", function)
        self.assertIn("repos/MahdiHedhli/LocalInferenceTestBench", function)
        self.assertIn('python3 "${helper}" repository', function)
        self.assertIn('--input "${destination}-repository.json"', function)
        self.assertIn("--require-auto-merge", function)
        self.assertIn("issues/comments/${MARKER_COMMENT_ID}", function)
        self.assertIn("review-states", function)
        self.assertIn("threads --input", function)
        self.assertIn('.commit.sha | strings', function)
        self.assertIn('test "${live_base}" = "${BASE_SHA}"', function)
        self.assertLess(identity, auto_merge_check)
        self.assertLess(auto_merge_check, auto_merge_mutation)
        self.assertLess(auto_merge_mutation, approval_check)
        self.assertLess(approval_check, approval_mutation)

    def test_reviewer_secret_is_explicit_and_bound_only_in_the_final_step(self) -> None:
        boundary = BOUNDARY_PATH.read_text(encoding="utf-8")
        workflow = AUTO_MERGE_PATH.read_text(encoding="utf-8")
        reviewer_secret_name = "reviewer_" + "token"

        self.assertEqual(boundary.count("secrets.ERNEST_REVIEW_TOKEN"), 1)
        self.assertEqual(boundary.count(reviewer_secret_name + ":"), 1)
        self.assertNotIn("secrets: inherit", boundary)
        self.assertNotIn("secrets: inherit", workflow)
        secret_reference = "secrets.reviewer_token"
        self.assertEqual(workflow.count(secret_reference), 1)
        prefix, suffix = workflow.split(secret_reference, 1)
        self.assertIn("Revalidate without reviewer credential", prefix)
        self.assertIn("--require-benchmark", prefix)
        self.assertNotIn(secret_reference, suffix)
        final_step = workflow[workflow.rfind("      - name: Arm protected squash") :]
        self.assertIn(f"GH_TOKEN: ${{{{ {secret_reference} }}}}", final_step)

    def test_untrusted_pull_request_metadata_never_becomes_the_squash_message(self) -> None:
        workflow = AUTO_MERGE_PATH.read_text(encoding="utf-8")

        self.assertNotIn("github.event.issue.title", workflow)
        self.assertNotIn("github.event.issue.body", workflow)
        self.assertNotIn("github.event.pull_request.title", workflow)
        self.assertNotIn("github.event.pull_request.body", workflow)
        self.assertIn('headline="data: add benchmark submission ${SUBMISSION_ID:0:12}"', workflow)
        self.assertIn("Schema-validated self-reported benchmark record; run unverified.", workflow)

    def test_pages_and_pr_jobs_both_require_a_deterministic_rebuild(self) -> None:
        pages = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        public_safety = (ROOT / ".github/workflows/public-safety.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("python3 scripts/build_leaderboard.py\n", pages)
        self.assertIn("git diff --exit-code -- site/data/leaderboard.json", pages)
        self.assertLess(
            pages.index("python3 scripts/build_leaderboard.py\n"),
            pages.index("git diff --exit-code -- site/data/leaderboard.json"),
        )
        self.assertIn("python3 scripts/build_leaderboard.py --check", public_safety)

    def test_expressions_are_never_interpolated_inside_shell_programs(self) -> None:
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

    def test_external_actions_are_sha_pinned_and_local_calls_are_same_commit(self) -> None:
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            for action in re.findall(r"(?m)^\s*uses:\s*([^\s#]+)", text):
                with self.subTest(workflow=path.name, action=action):
                    if action.startswith("./"):
                        self.assertEqual(
                            action,
                            "./.github/workflows/trusted-benchmark-auto-merge.yml",
                        )
                    else:
                        self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
