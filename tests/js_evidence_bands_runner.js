"use strict";

const fs = require("fs");
const path = require("path");

const [appSource, leaderboardSource] = process.argv.slice(2);
if (!appSource || !leaderboardSource) {
  process.exitCode = 2;
} else {
  const {
    computeConfigCellDigest,
    createShardRankingState,
    displayRankBands,
    entryScoreIntervals,
    plausibilityEvidenceText,
    scoreEvidenceText,
    sortedEntries,
    validateAndTrackShardRanking,
    validateEntry,
    validateFullRankBands,
    validateParameterScale,
    validatePayload,
    wilsonInterval,
  } = require(path.resolve(appSource));
  const legacy = JSON.parse(fs.readFileSync(leaderboardSource, "utf8"));

  (async () => {

  async function accepts(callback) {
    try {
      await callback();
      return true;
    } catch (error) {
      return false;
    }
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function hardwareClass(hardware) {
    if (hardware.execution_mode === "cpu_only") {
      return "cpu_only";
    }
    if (!["accelerator_only", "hybrid"].includes(hardware.execution_mode)) {
      return "unknown";
    }
    return `${hardware.memory.architecture}_accelerator`;
  }

  function projectedEntry(source) {
    const latency = source.metrics.latency_ms_mean;
    const throughput = source.metrics.completion_tokens_per_second;
    return {
      ...clone(source),
      rank: 1,
      facet_id: "all-cases-text",
      config_cell: {
        key_version: "1.0",
        selection_version: "1.0",
        digest: "f".repeat(64),
      },
      corroboration: {
        accepted_record_count: 1,
        by_validity: {
          clean: { count: 0, earliest_period: null, latest_period: null },
          nonquiescent: { count: 0, earliest_period: null, latest_period: null },
          degraded_midrun: { count: 0, earliest_period: null, latest_period: null },
          legacy_unreported: { count: 1, earliest_period: null, latest_period: null },
        },
      },
      score_intervals: {
        method: "wilson_95",
        semantic: wilsonInterval(
          source.metrics.semantic_pass_count,
          source.metrics.scored_case_count,
        ),
        exact_format: wilsonInterval(
          source.metrics.exact_format_pass_count,
          source.metrics.scored_case_count,
        ),
      },
      performance_distribution: {
        latency_ms_mean: {
          sample_count: 1,
          median: latency,
          minimum: latency,
          maximum: latency,
        },
        completion_tokens_per_second:
          throughput === null
            ? { sample_count: 0, median: null, minimum: null, maximum: null }
            : {
                sample_count: 1,
                median: throughput,
                minimum: throughput,
                maximum: throughput,
              },
      },
      plausibility: {
        policy_version: "1.0",
        status: "not_evaluated",
        basis: {
          hardware_class: hardwareClass(source.hardware),
          model_size_bucket: "unknown",
          model_size_basis: "unknown",
        },
        evaluated_record_count: 0,
        outside_envelope_record_count: 0,
        signals: [],
      },
      submission_schema_version: "1.0",
      validity: "legacy_unreported",
      measurement_period: null,
      measurement_conditions: null,
      model: {
        ...clone(source.model),
        parameter_scale: { total_billions: null, active_billions: null },
      },
    };
  }

  function rankFixture(id, semantic, exact, rank) {
    return {
      facet_id: "all-cases-text",
      profile: "standard",
      suite_version: "1.0",
      config_cell: { digest: id.repeat(64) },
      submission_id: id.repeat(64),
      rank,
      score_intervals: {
        semantic: { lower_percent: semantic[0], upper_percent: semantic[1] },
        exact_format: { lower_percent: exact[0], upper_percent: exact[1] },
      },
    };
  }

  const entry = projectedEntry(legacy.entries[0]);
  entry.config_cell.digest = await computeConfigCellDigest(entry);
  const badDigest = clone(entry);
  badDigest.config_cell.digest = "f".repeat(64);
  if (badDigest.config_cell.digest === entry.config_cell.digest) {
    badDigest.config_cell.digest = "e".repeat(64);
  }
  const tamperedWilson = clone(entry);
  tamperedWilson.score_intervals.semantic.lower_percent += 1;
  const badCorroboration = clone(entry);
  badCorroboration.corroboration.accepted_record_count = 2;
  const badDistribution = clone(entry);
  badDistribution.performance_distribution.latency_ms_mean.minimum =
    badDistribution.performance_distribution.latency_ms_mean.maximum + 1;
  const badBasis = clone(entry);
  badBasis.plausibility.basis.model_size_bucket = "under_4b";
  const badSignals = clone(entry);
  badSignals.model.parameter_scale = { total_billions: 7, active_billions: 7 };
  badSignals.plausibility = {
    ...badSignals.plausibility,
    status: "caution",
    basis: {
      ...badSignals.plausibility.basis,
      model_size_bucket: "4b_to_under_14b",
      model_size_basis: "active_billions",
    },
    evaluated_record_count: 1,
    outside_envelope_record_count: 1,
    signals: ["throughput_above_envelope", "latency_below_envelope"],
  };
  const caution = clone(entry);
  caution.hardware.execution_mode = "hybrid";
  caution.model.parameter_scale = { total_billions: 7, active_billions: 7 };
  caution.metrics.latency_ms_mean = 0;
  caution.performance_distribution.latency_ms_mean = {
    sample_count: 1,
    median: 0,
    minimum: 0,
    maximum: 0,
  };
  caution.plausibility = {
    policy_version: "1.0",
    status: "caution",
    basis: {
      hardware_class: hardwareClass(caution.hardware),
      model_size_bucket: "4b_to_under_14b",
      model_size_basis: "active_billions",
    },
    evaluated_record_count: 1,
    outside_envelope_record_count: 1,
    signals: ["latency_below_envelope"],
  };

  const bandEntries = [
    rankFixture("a", [70, 90], [80, 95], 1),
    rankFixture("b", [55, 75], [65, 85], 1),
    rankFixture("c", [40, 60], [50, 70], 1),
    rankFixture("d", [45, 65], [0, 20], 2),
    rankFixture("e", [0, 20], [80, 100], 3),
  ];
  const tamperedBands = clone(bandEntries);
  tamperedBands[2].rank = 2;
  const duplicateCell = clone(bandEntries);
  duplicateCell[1].config_cell.digest = duplicateCell[0].config_cell.digest;
  const nameIndependent = clone(bandEntries);
  nameIndependent.forEach((item, index) => {
    item.model = { display_name: `${String.fromCharCode(90 - index)} model` };
  });
  const partialState = createShardRankingState();
  const partialBandsAccepted =
    validateAndTrackShardRanking(partialState, bandEntries.slice(0, 2)) &&
    validateAndTrackShardRanking(partialState, bandEntries.slice(2), true);
  const tamperedShardState = createShardRankingState();
  const tamperedShardBandsRejected = !validateAndTrackShardRanking(
    tamperedShardState,
    [
      rankFixture("f", [56, 100], [56, 100], 1),
      rankFixture("g", [56, 100], [56, 100], 2),
    ],
    true,
  );
  const bridgeState = createShardRankingState();
  const delayedBridgeAccepted =
    validateAndTrackShardRanking(
      bridgeState,
      [
        rankFixture("h", [80, 100], [80, 100], 1),
        rankFixture("i", [40, 60], [40, 60], 1),
      ],
    ) &&
    validateAndTrackShardRanking(
      bridgeState,
      [rankFixture("j", [55, 85], [55, 85], 1)],
      true,
    );
  const legacyBands = displayRankBands(legacy.entries);
  const neutralHigh = clone(entry);
  neutralHigh.submission_id = "f".repeat(64);
  neutralHigh.metrics.exact_format_pass_count = 5;
  neutralHigh.metrics.exact_format_score_percent = 100;
  const neutralLow = clone(entry);
  neutralLow.submission_id = "a".repeat(64);
  neutralLow.metrics.exact_format_pass_count = 0;
  neutralLow.metrics.exact_format_score_percent = 0;
  const neutralDefaultOrder = sortedEntries(
    [neutralHigh, neutralLow],
    "semantic",
    new Map([
      [neutralHigh.submission_id, 1],
      [neutralLow.submission_id, 1],
    ]),
  );

  const results = {
    wilson_five_of_five: wilsonInterval(5, 5),
    wilson_zero_of_five: wilsonInterval(0, 5),
    legacy_wilson_in_memory: entryScoreIntervals(legacy.entries[0]).semantic,
    legacy_score_text: scoreEvidenceText(legacy.entries[0], "semantic"),
    legacy_display_band_count: new Set(legacyBands.values()).size,
    valid_projected_entry: validateEntry(entry, "1.1"),
    valid_projected_payload: await accepts(() =>
      validatePayload({ schema_version: "1.1", entry_count: 1, entries: [entry] }),
    ),
    tampered_config_digest_rejected: !(await accepts(() =>
      validatePayload({ schema_version: "1.1", entry_count: 1, entries: [badDigest] }),
    )),
    tampered_wilson_rejected: !validateEntry(tamperedWilson, "1.1"),
    corroboration_arithmetic_rejected: !validateEntry(badCorroboration, "1.1"),
    distribution_order_rejected: !validateEntry(badDistribution, "1.1"),
    plausibility_basis_rejected: !validateEntry(badBasis, "1.1"),
    signal_order_rejected: !validateEntry(badSignals, "1.1"),
    caution_remains_valid: validateEntry(caution, "1.1"),
    caution_text_is_non_attesting:
      plausibilityEvidenceText(caution).includes("this is not verification") &&
      plausibilityEvidenceText(caution).includes("remains published"),
    parameter_scale_valid: validateParameterScale({
      total_billions: 46.7,
      active_billions: 12.25,
    }),
    parameter_scale_precision_rejected: !validateParameterScale({
      total_billions: 7.0001,
      active_billions: null,
    }),
    parameter_scale_active_without_total_rejected: !validateParameterScale({
      total_billions: null,
      active_billions: 3,
    }),
    parameter_scale_active_above_total_rejected: !validateParameterScale({
      total_billions: 7,
      active_billions: 8,
    }),
    transitive_rank_bands: validateFullRankBands(bandEntries),
    tampered_rank_band_rejected: !validateFullRankBands(tamperedBands),
    duplicate_config_cell_rejected: !validateFullRankBands(duplicateCell),
    names_do_not_change_bands: validateFullRankBands(nameIndependent),
    partial_rank_bands_are_monotonic: partialBandsAccepted,
    tampered_shard_rank_band_rejected: tamperedShardBandsRejected,
    delayed_shard_bridge_accepted: delayedBridgeAccepted,
    neutral_default_tiebreak:
      neutralDefaultOrder[0].submission_id === neutralLow.submission_id,
  };
  process.stdout.write(JSON.stringify(results));
  })().catch((error) => {
    process.stderr.write(`${error.stack || error}\n`);
    process.exitCode = 1;
  });
}
