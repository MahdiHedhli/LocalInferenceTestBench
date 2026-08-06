"use strict";

const [appSource] = process.argv.slice(2);
if (!appSource) {
  process.exit(2);
}

const { filterEntriesByValidity } = require(appSource);
const entries = [
  { validity: "clean", measurement_period: "2026-01" },
  { validity: "nonquiescent", measurement_period: "2026-01" },
  { validity: "degraded_midrun", measurement_period: "2026-02" },
  {},
];

process.stdout.write(
  JSON.stringify({
    clean_default: filterEntriesByValidity(entries).length,
    all: filterEntriesByValidity(entries, "all").length,
    legacy: filterEntriesByValidity(entries, "legacy_unreported").length,
    month: filterEntriesByValidity(entries, "all", "2026-01").length,
  }),
);
