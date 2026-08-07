"use strict";

const fs = require("fs");
const path = require("path");

const [appSource, leaderboardSource] = process.argv.slice(2);
if (!appSource || !leaderboardSource) {
  process.exitCode = 2;
} else {
  const {
    createShardRankingState,
    fetchBoundedJson,
    validateAndTrackShardRanking,
  } = require(path.resolve(appSource));
  const leaderboard = JSON.parse(fs.readFileSync(leaderboardSource, "utf8"));

  function syntheticLegacyEntries() {
    // Structural shard tests must not depend on the live board's Wilson-band
    // layout (schema 1.1 can legitimately collapse every entry into rank 1).
    // Use a closed legacy-shaped fixture with a same-rank prefix and a later rank.
    const metrics = (semantic, exact) => ({
      case_count: 5,
      scored_case_count: 5,
      semantic_pass_count: semantic,
      exact_format_pass_count: exact,
      semantic_score_percent: semantic * 20,
      exact_format_score_percent: exact * 20,
      usage_coverage_cases: 5,
      completion_tokens_per_second: 10.0,
      latency_ms_mean: 1000.0,
    });
    const base = {
      profile: "standard",
      suite_version: "1.0",
      hardware: {
        cpu: { model: "Synthetic CPU", logical_cores: 4 },
        memory: { system_gb: 16.0, architecture: "unknown" },
        accelerators: [],
        execution_mode: "unknown",
      },
      runtime: { name: "Synthetic Runtime", version: "1.0.0", backend: "test" },
      model: {
        display_name: "Synthetic Model",
        source: "synthetic/model",
        precision: "test",
        declared_context_tokens: 4096,
        revision: "synthetic-revision",
      },
      settings: {
        temperature: 0.0,
        top_p: 1.0,
        max_output_tokens: 256,
        seed: 0,
      },
    };
    return [
      {
        ...base,
        rank: 1,
        submission_id:
          "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        metrics: metrics(5, 5),
      },
      {
        ...base,
        rank: 1,
        submission_id:
          "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        metrics: metrics(5, 5),
      },
      {
        ...base,
        rank: 2,
        submission_id:
          "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        metrics: metrics(4, 4),
      },
      {
        ...base,
        rank: 2,
        submission_id:
          "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        metrics: metrics(4, 4),
      },
    ];
  }

  async function timeoutIsBounded() {
    const originalFetch = global.fetch;
    let capturedOptions = null;
    global.fetch = (_url, options) => {
      capturedOptions = options;
      return new Promise((_resolve, reject) => {
        options.signal.addEventListener(
          "abort",
          () => reject(new Error("request aborted")),
          { once: true },
        );
      });
    };
    try {
      await fetchBoundedJson("./data/leaderboard.json", 5);
      return false;
    } catch (error) {
      return (
        capturedOptions !== null &&
        capturedOptions.cache === "no-cache" &&
        capturedOptions.credentials === "omit" &&
        capturedOptions.signal.aborted
      );
    } finally {
      global.fetch = originalFetch;
    }
  }

  async function fetchedBytesAreAccepted(bytes) {
    const originalFetch = global.fetch;
    global.fetch = async () => ({
      ok: true,
      headers: { get: () => String(bytes.byteLength) },
      arrayBuffer: async () =>
        bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
    });
    try {
      await fetchBoundedJson("./data/leaderboard.json", 50);
      return true;
    } catch (error) {
      return false;
    } finally {
      global.fetch = originalFetch;
    }
  }

  async function main() {
    if (!Array.isArray(leaderboard.entries) || leaderboard.entries.length < 1) {
      throw new Error("The loading fixture requires a non-empty committed leaderboard.");
    }
    const entries = syntheticLegacyEntries();
    const split = entries.findIndex((entry) => entry.rank > entries[0].rank);
    if (split < 2) {
      throw new Error("The loading fixture requires a same-rank boundary and a later rank.");
    }

    const incremental = createShardRankingState();
    const firstSegmentAccepted = validateAndTrackShardRanking(
      incremental,
      entries.slice(0, split),
    );
    const secondSegmentAccepted = validateAndTrackShardRanking(
      incremental,
      entries.slice(split),
    );

    const wrongFirstRank = createShardRankingState();
    const wrongFirst = JSON.parse(JSON.stringify(entries[0]));
    wrongFirst.rank += 1;

    const duplicate = createShardRankingState();
    validateAndTrackShardRanking(duplicate, [entries[0]]);
    const duplicateRejected = !validateAndTrackShardRanking(duplicate, [entries[0]]);

    const reversedBoundary = createShardRankingState();
    validateAndTrackShardRanking(reversedBoundary, [entries[1]]);
    const reversedBoundaryRejected = !validateAndTrackShardRanking(
      reversedBoundary,
      [entries[0]],
    );

    const wrongRankBoundary = createShardRankingState();
    validateAndTrackShardRanking(wrongRankBoundary, entries.slice(0, split));
    const wrongRank = JSON.parse(JSON.stringify(entries[split]));
    wrongRank.rank += 1;

    const freshState = createShardRankingState();
    const freshStateAcceptsPreviouslySeenId = validateAndTrackShardRanking(
      freshState,
      [entries[0]],
    );

    const results = {
      bounded_timeout: await timeoutIsBounded(),
      fetched_valid_utf8_accepted: await fetchedBytesAreAccepted(
        Buffer.from('{"value":1}', "utf8"),
      ),
      fetched_duplicate_rejected: !(await fetchedBytesAreAccepted(
        Buffer.from('{"value":1,"value":1}', "utf8"),
      )),
      fetched_bom_rejected: !(await fetchedBytesAreAccepted(
        Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from('{"value":1}')]),
      )),
      fetched_invalid_utf8_rejected: !(await fetchedBytesAreAccepted(
        Buffer.from([0x7b, 0x22, 0x78, 0x22, 0x3a, 0xff, 0x7d]),
      )),
      duplicate_rejected_without_mutation:
        duplicateRejected && duplicate.entryCount === 1,
      first_rank_required: !validateAndTrackShardRanking(wrongFirstRank, [wrongFirst]),
      fresh_state_accepts_previously_seen_id: freshStateAcceptsPreviouslySeenId,
      incremental_segments:
        firstSegmentAccepted &&
        secondSegmentAccepted &&
        incremental.entryCount === entries.length,
      reversed_canonical_boundary_rejected: reversedBoundaryRejected,
      wrong_rank_boundary_rejected: !validateAndTrackShardRanking(
        wrongRankBoundary,
        [wrongRank],
      ),
    };
    process.stdout.write(JSON.stringify(results));
  }

  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
