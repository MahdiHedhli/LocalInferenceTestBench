"use strict";

const [appSource] = process.argv.slice(2);
if (!appSource) {
  process.exit(2);
}

const { scorePercent, sortedEntries } = require(appSource);

function entry(id, latency) {
  return {
    id,
    metrics: {
      exact_format_score_percent: 100,
      semantic_score_percent: 100,
      latency_ms_mean: latency,
      completion_tokens_per_second: null,
    },
    model: { declared_context_tokens: 4096 },
  };
}

const ordered = sortedEntries(
  [entry("unavailable", null), entry("slow", 20), entry("fast", 10)],
  "latency",
);
process.stdout.write(
  `${JSON.stringify({
    latency_order: ordered.map((item) => item.id),
    half_up_scores: [scorePercent(1, 16), scorePercent(15, 16)],
  })}\n`,
);
