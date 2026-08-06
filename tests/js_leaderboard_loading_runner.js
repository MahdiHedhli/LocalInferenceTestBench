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

  async function main() {
    if (!Array.isArray(leaderboard.entries) || leaderboard.entries.length < 4) {
      throw new Error("The loading fixture requires at least four ranked entries.");
    }
    const entries = leaderboard.entries;
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
      duplicate_rejected_without_mutation:
        duplicateRejected && duplicate.entryCount === 1,
      first_rank_required: !validateAndTrackShardRanking(wrongFirstRank, [wrongFirst]),
      fresh_state_accepts_previously_seen_id: freshStateAcceptsPreviouslySeenId,
      incremental_segments:
        firstSegmentAccepted &&
        secondSegmentAccepted &&
        incremental.entryCount === leaderboard.entry_count,
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
