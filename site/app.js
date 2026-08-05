"use strict";

const DATA_URL = "./data/leaderboard.json";
const MAX_DATA_BYTES = 2 * 1024 * 1024;
const MAX_ENTRIES = 10_000;
const MAX_SUBMISSION_BYTES = 256 * 1024;
const STANDARD_CASE_IDS = [
  "structured-json",
  "python-ast",
  "defensive-triage",
  "read-only-tool",
  "unapproved-change-boundary",
];
const OUTCOMES = new Set(["pass", "semantic_only", "format_only", "fail", "not_scored"]);
const ROUTES = new Set([
  "direct_response",
  "read_only_tool",
  "safe_refusal",
  "unsafe_mutation",
  "unexpected_tool",
  "unrecognized",
]);
const TERMINATIONS = new Set([
  "completed",
  "tool_call",
  "filtered",
  "cancelled",
  "output_budget",
  "context_window",
  "length_unknown",
  "reasoning_only",
  "unknown",
  "other",
  "timeout",
  "network_error",
  "authentication",
  "rate_limited",
  "server_error",
  "request_rejected",
  "invalid_json",
  "protocol_error",
  "response_too_large",
  "http_error",
]);
const MEMORY_ARCHITECTURES = new Set(["shared", "discrete", "mixed", "unknown"]);
const ACCELERATOR_KINDS = new Set([
  "integrated_gpu",
  "discrete_gpu",
  "neural_accelerator",
  "other",
]);
const EXECUTION_MODES = new Set(["cpu_only", "accelerator_only", "hybrid", "unknown"]);
const DESCRIPTOR_UUID = /(?:^|[^0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:$|[^0-9a-f])/iu;
const DESCRIPTOR_LABEL = /\b(?:s\s*\/?\s*n|serial(?:\s+(?:number|no|id))?|inventory\s+(?:id|tag)|asset\s+(?:id|tag)|device\s+uuid|machine\s+(?:id|name)|host\s*name|user\s*name|account\s+(?:id|name))\b/iu;
const DESCRIPTOR_NETWORK = /(?:^|[^0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?:$|[^0-9.])|(?:^|[^0-9a-f:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?:%[a-z0-9_.-]+)?(?:$|[^0-9a-f:])/iu;
const DESCRIPTOR_URL_OR_EMAIL = /\b[a-z][a-z0-9+.-]*:\/\/|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/iu;

const elements = {
  body: document.querySelector("#leaderboard-body"),
  filters: document.querySelector("#leaderboard-filters"),
  hardwareFilter: document.querySelector("#hardware-filter"),
  search: document.querySelector("#model-search"),
  sort: document.querySelector("#sort-results"),
  status: document.querySelector("#leaderboard-status"),
  table: document.querySelector("#leaderboard-table-shell"),
  updated: document.querySelector("#leaderboard-updated"),
  submissionFile: document.querySelector("#submission-file"),
  submissionStatus: document.querySelector("#submission-status"),
  submissionPreview: document.querySelector("#submission-preview"),
  previewProfile: document.querySelector("#preview-profile"),
  previewModel: document.querySelector("#preview-model"),
  previewSuite: document.querySelector("#preview-suite"),
  previewHardware: document.querySelector("#preview-hardware"),
  copySubmission: document.querySelector("#copy-submission"),
  downloadSubmission: document.querySelector("#download-submission"),
  continueSubmission: document.querySelector("#continue-submission"),
};

let entries = [];
let checkedSubmission = null;
let checkedSubmissionText = "";

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function hasExactKeys(value, required, optional = []) {
  if (!isRecord(value)) {
    return false;
  }
  const keys = Object.keys(value);
  const allowed = new Set([...required, ...optional]);
  return required.every((key) => Object.hasOwn(value, key)) && keys.every((key) => allowed.has(key));
}

function isInteger(value, minimum, maximum = Number.MAX_SAFE_INTEGER) {
  return Number.isSafeInteger(value) && value >= minimum && value <= maximum;
}

function isFiniteNumber(value, minimum, maximum = Number.MAX_VALUE) {
  return Number.isFinite(value) && value >= minimum && value <= maximum;
}

function isPublicText(value, maximum = 500) {
  return (
    typeof value === "string" &&
    value.length >= 1 &&
    value.length <= maximum &&
    !/[\u0000-\u001f\u007f-\u009f\u200e\u200f\u2028-\u202e\u2066-\u2069\ud800-\udfff]/u.test(value)
  );
}

function isPublicDescriptorText(value, maximum) {
  return (
    isPublicText(value, maximum) &&
    !DESCRIPTOR_UUID.test(value) &&
    !DESCRIPTOR_LABEL.test(value) &&
    !DESCRIPTOR_NETWORK.test(value) &&
    !DESCRIPTOR_URL_OR_EMAIL.test(value)
  );
}

function validateModel(model) {
  if (
    !hasExactKeys(
      model,
      ["display_name", "source", "precision", "declared_context_tokens"],
      ["revision", "digest"],
    )
  ) {
    return false;
  }
  const identityFields = ["revision", "digest"].filter((key) => Object.hasOwn(model, key));
  return (
    identityFields.length === 1 &&
    isPublicText(model.display_name) &&
    isPublicText(model.source) &&
    isPublicText(model.precision) &&
    isPublicText(model[identityFields[0]], 200) &&
    isInteger(model.declared_context_tokens, 1)
  );
}

function validateHardware(hardware) {
  if (!hasExactKeys(hardware, ["cpu", "memory", "accelerators", "execution_mode"])) {
    return false;
  }
  const cpu = hardware.cpu;
  const memory = hardware.memory;
  if (
    !hasExactKeys(cpu, ["model", "logical_cores"]) ||
    !isPublicDescriptorText(cpu.model, 200) ||
    !isInteger(cpu.logical_cores, 1, 4096) ||
    !hasExactKeys(memory, ["system_gb", "architecture"]) ||
    !isFiniteNumber(memory.system_gb, 0.1, 1_000_000) ||
    !hasOneDecimalPlace(memory.system_gb) ||
    !MEMORY_ARCHITECTURES.has(memory.architecture) ||
    !EXECUTION_MODES.has(hardware.execution_mode) ||
    !Array.isArray(hardware.accelerators) ||
    hardware.accelerators.length > 8
  ) {
    return false;
  }
  const seenAccelerators = new Set();
  const acceleratorsValid = hardware.accelerators.every((accelerator) => {
    if (!hasExactKeys(accelerator, ["kind", "model", "count", "memory_gb"])) {
      return false;
    }
    const identity = JSON.stringify([
      accelerator.kind,
      typeof accelerator.model === "string" ? accelerator.model.toLocaleLowerCase() : "",
      accelerator.count,
      accelerator.memory_gb,
    ]);
    const valid = (
      ACCELERATOR_KINDS.has(accelerator.kind) &&
      isPublicDescriptorText(accelerator.model, 200) &&
      isInteger(accelerator.count, 1, 64) &&
      (accelerator.memory_gb === null ||
        (isFiniteNumber(accelerator.memory_gb, 0.1, 1_000_000) &&
          hasOneDecimalPlace(accelerator.memory_gb)))
    );
    if (!valid || seenAccelerators.has(identity)) {
      return false;
    }
    seenAccelerators.add(identity);
    return true;
  });
  if (!acceleratorsValid) {
    return false;
  }
  if (hardware.execution_mode === "cpu_only" && hardware.accelerators.length !== 0) {
    return false;
  }
  if (
    ["accelerator_only", "hybrid"].includes(hardware.execution_mode) &&
    hardware.accelerators.length === 0
  ) {
    return false;
  }
  if (
    memory.architecture === "shared" &&
    hardware.accelerators.some((accelerator) => accelerator.memory_gb !== null)
  ) {
    return false;
  }
  if (
    memory.architecture === "discrete" &&
    hardware.accelerators.some((accelerator) => accelerator.memory_gb === null)
  ) {
    return false;
  }
  return true;
}

function validateRuntime(runtime) {
  return (
    hasExactKeys(runtime, ["name", "version", "backend"]) &&
    isPublicDescriptorText(runtime.name, 100) &&
    isPublicDescriptorText(runtime.version, 100) &&
    isPublicDescriptorText(runtime.backend, 100)
  );
}

function validateSettings(settings, contextTokens) {
  return (
    hasExactKeys(settings, ["temperature", "top_p", "max_output_tokens", "seed"]) &&
    isFiniteNumber(settings.temperature, 0, 2) &&
    hasAtMostSixDecimalPlaces(settings.temperature) &&
    isFiniteNumber(settings.top_p, Number.MIN_VALUE, 1) &&
    hasAtMostSixDecimalPlaces(settings.top_p) &&
    isInteger(settings.max_output_tokens, 1, contextTokens) &&
    (settings.seed === null || Number.isSafeInteger(settings.seed))
  );
}

function validateMetrics(metrics) {
  if (
    !hasExactKeys(metrics, [
      "case_count",
      "semantic_pass_count",
      "semantic_score_percent",
      "exact_format_pass_count",
      "exact_format_score_percent",
      "scored_case_count",
      "usage_coverage_cases",
      "latency_ms_mean",
      "completion_tokens_per_second",
    ])
  ) {
    return false;
  }
  const semanticPercent = Math.round((metrics.semantic_pass_count / STANDARD_CASE_IDS.length) * 1000) / 10;
  const formatPercent = Math.round((metrics.exact_format_pass_count / STANDARD_CASE_IDS.length) * 1000) / 10;
  return (
    metrics.case_count === STANDARD_CASE_IDS.length &&
    metrics.scored_case_count === STANDARD_CASE_IDS.length &&
    isInteger(metrics.semantic_pass_count, 0, metrics.scored_case_count) &&
    isInteger(metrics.exact_format_pass_count, 0, metrics.scored_case_count) &&
    isInteger(metrics.usage_coverage_cases, 0, metrics.case_count) &&
    isFiniteNumber(metrics.semantic_score_percent, 0, 100) &&
    isFiniteNumber(metrics.exact_format_score_percent, 0, 100) &&
    metrics.semantic_score_percent === semanticPercent &&
    metrics.exact_format_score_percent === formatPercent &&
    hasOneDecimalPlace(metrics.latency_ms_mean) &&
    (metrics.completion_tokens_per_second === null ||
      (hasOneDecimalPlace(metrics.completion_tokens_per_second) &&
        metrics.usage_coverage_cases === STANDARD_CASE_IDS.length))
  );
}

function validateEntry(entry) {
  return (
    hasExactKeys(entry, [
      "rank",
      "submission_id",
      "suite_version",
      "profile",
      "hardware",
      "runtime",
      "model",
      "settings",
      "metrics",
    ]) &&
    isInteger(entry.rank, 1) &&
    typeof entry.submission_id === "string" &&
    /^[a-f0-9]{64}$/u.test(entry.submission_id) &&
    entry.suite_version === "1.0" &&
    entry.profile === "standard" &&
    validateHardware(entry.hardware) &&
    validateRuntime(entry.runtime) &&
    validateModel(entry.model) &&
    validateSettings(entry.settings, entry.model.declared_context_tokens) &&
    validateMetrics(entry.metrics)
  );
}

function validatePayload(payload) {
  if (
    !hasExactKeys(payload, ["schema_version", "entry_count", "entries"]) ||
    payload.schema_version !== "1.0" ||
    !isInteger(payload.entry_count, 0, MAX_ENTRIES) ||
    !Array.isArray(payload.entries) ||
    payload.entries.length !== payload.entry_count ||
    !payload.entries.every(validateEntry) ||
    !validateRanking(payload.entries)
  ) {
    throw new Error("Leaderboard data does not match the expected public schema.");
  }
  return payload;
}

function validateRanking(values) {
  const seen = new Set();
  let previousQuality = null;
  let expectedRank = 0;
  for (const entry of values) {
    if (seen.has(entry.submission_id)) {
      return false;
    }
    seen.add(entry.submission_id);
    const quality = [
      entry.metrics.semantic_score_percent,
      entry.metrics.exact_format_score_percent,
    ];
    if (
      previousQuality &&
      (quality[0] > previousQuality[0] ||
        (quality[0] === previousQuality[0] && quality[1] > previousQuality[1]))
    ) {
      return false;
    }
    if (!previousQuality || quality[0] !== previousQuality[0] || quality[1] !== previousQuality[1]) {
      expectedRank += 1;
    }
    if (entry.rank !== expectedRank) {
      return false;
    }
    previousQuality = quality;
  }
  return true;
}

function hasAtMostSixDecimalPlaces(value) {
  return Number.isFinite(value) && Number(value.toFixed(6)) === value;
}

function hasOneDecimalPlace(value) {
  return (
    isFiniteNumber(value, 0, 1_000_000_000) &&
    Math.abs(value * 10 - Math.round(value * 10)) < 1e-9
  );
}

function validateCases(cases) {
  if (!Array.isArray(cases) || cases.length !== STANDARD_CASE_IDS.length) {
    return false;
  }
  return cases.every((item, index) => {
    if (!hasExactKeys(item, ["case_id", "outcome", "route", "termination"])) {
      return false;
    }
    const unsafePass =
      item.route === "unsafe_mutation" && ["pass", "semantic_only"].includes(item.outcome);
    return (
      item.case_id === STANDARD_CASE_IDS[index] &&
      OUTCOMES.has(item.outcome) &&
      ROUTES.has(item.route) &&
      TERMINATIONS.has(item.termination) &&
      !unsafePass
    );
  });
}

function validateSubmissionMetrics(metrics, cases) {
  if (
    !hasExactKeys(metrics, [
      "case_count",
      "semantic_pass_count",
      "exact_format_pass_count",
      "scored_case_count",
      "usage_coverage_cases",
      "latency_ms_mean",
      "completion_tokens_per_second",
    ])
  ) {
    return false;
  }
  const semanticCount = cases.filter((item) => ["pass", "semantic_only"].includes(item.outcome)).length;
  const formatCount = cases.filter((item) => ["pass", "format_only"].includes(item.outcome)).length;
  const scoredCount = cases.filter((item) => item.outcome !== "not_scored").length;
  const throughput = metrics.completion_tokens_per_second;
  return (
    metrics.case_count === STANDARD_CASE_IDS.length &&
    metrics.semantic_pass_count === semanticCount &&
    metrics.exact_format_pass_count === formatCount &&
    metrics.scored_case_count === scoredCount &&
    scoredCount === STANDARD_CASE_IDS.length &&
    isInteger(metrics.usage_coverage_cases, 0, STANDARD_CASE_IDS.length) &&
    hasOneDecimalPlace(metrics.latency_ms_mean) &&
    (throughput === null ||
      (hasOneDecimalPlace(throughput) && metrics.usage_coverage_cases === STANDARD_CASE_IDS.length))
  );
}

function validateSubmission(submission) {
  if (
    !hasExactKeys(submission, [
      "schema_version",
      "submission_id",
      "suite_version",
      "profile",
      "hardware",
      "runtime",
      "model",
      "settings",
      "cases",
      "metrics",
    ]) ||
    submission.schema_version !== "1.0" ||
    submission.suite_version !== "1.0" ||
    submission.profile !== "standard" ||
    typeof submission.submission_id !== "string" ||
    !/^[a-f0-9]{64}$/u.test(submission.submission_id) ||
    !validateHardware(submission.hardware) ||
    !validateRuntime(submission.runtime) ||
    !validateModel(submission.model) ||
    !validateSettings(submission.settings, submission.model.declared_context_tokens) ||
    !validateCases(submission.cases) ||
    !validateSubmissionMetrics(submission.metrics, submission.cases)
  ) {
    throw new Error("Submission data does not match the minimized public schema.");
  }
  return submission;
}

function makeElement(tagName, text, className) {
  const element = document.createElement(tagName);
  if (text !== undefined) {
    element.textContent = text;
  }
  if (className) {
    element.className = className;
  }
  return element;
}

function percentage(value) {
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)}%`;
}

function decimal(value) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value);
}

function settingNumber(value) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(value);
}

function integer(value) {
  return new Intl.NumberFormat().format(value);
}

function identityLabel(model) {
  if (Object.hasOwn(model, "revision")) {
    return `revision ${model.revision}`;
  }
  return `digest ${model.digest}`;
}

function readableEnum(value) {
  return value
    .split("_")
    .map((word, index) => {
      if (["cpu", "gpu"].includes(word)) {
        return word.toUpperCase();
      }
      return index === 0 ? `${word.charAt(0).toUpperCase()}${word.slice(1)}` : word;
    })
    .join(" ");
}

function acceleratorSummary(hardware) {
  if (hardware.accelerators.length === 0 || hardware.execution_mode === "cpu_only") {
    return `CPU: ${hardware.cpu.model}`;
  }
  return hardware.accelerators
    .map((accelerator) => `${accelerator.count} x ${accelerator.model}`)
    .join("; ");
}

function addDefinition(list, term, description) {
  list.append(makeElement("dt", term), makeElement("dd", description));
}

function addHardwareCell(row, entry) {
  const cell = makeElement("td", undefined, "hardware-cell");
  const details = document.createElement("details");
  details.append(makeElement("summary", acceleratorSummary(entry.hardware)));
  const list = makeElement("dl", undefined, "hardware-details");
  addDefinition(
    list,
    "CPU",
    `${entry.hardware.cpu.model}, ${integer(entry.hardware.cpu.logical_cores)} logical cores`,
  );
  addDefinition(
    list,
    "Memory",
    `${decimal(entry.hardware.memory.system_gb)} GB, ${readableEnum(entry.hardware.memory.architecture)}`,
  );
  addDefinition(list, "Execution", readableEnum(entry.hardware.execution_mode));
  const acceleratorText = entry.hardware.accelerators.length
    ? entry.hardware.accelerators
        .map((accelerator) => {
          const memory =
            accelerator.memory_gb === null
              ? "memory not reported"
              : `${decimal(accelerator.memory_gb)} GB each`;
          return `${accelerator.count} x ${accelerator.model}, ${readableEnum(accelerator.kind)}, ${memory}`;
        })
        .join("; ")
    : "None used";
  addDefinition(list, "Accelerators", acceleratorText);
  addDefinition(
    list,
    "Runtime",
    `${entry.runtime.name} ${entry.runtime.version}, ${entry.runtime.backend}`,
  );
  details.append(list);
  cell.append(
    details,
    makeElement(
      "span",
      `${decimal(entry.hardware.memory.system_gb)} GB | ${entry.runtime.name} ${entry.runtime.version}`,
      "cell-note",
    ),
  );
  row.append(cell);
}

function hardwareCategories(entry) {
  if (entry.hardware.accelerators.length === 0 || entry.hardware.execution_mode === "cpu_only") {
    return ["cpu_only"];
  }
  return [...new Set(entry.hardware.accelerators.map((accelerator) => accelerator.kind))];
}

function populateHardwareFilter(values) {
  const selected = elements.hardwareFilter.value;
  const categories = [...new Set(values.flatMap(hardwareCategories))].sort();
  const all = makeElement("option", "All hardware");
  all.value = "all";
  elements.hardwareFilter.replaceChildren(all);
  for (const category of categories) {
    const option = makeElement("option", readableEnum(category));
    option.value = category;
    elements.hardwareFilter.append(option);
  }
  elements.hardwareFilter.value = categories.includes(selected) ? selected : "all";
}

function addCell(row, primary, secondary, className) {
  const cell = makeElement("td", undefined, className);
  cell.append(makeElement("span", primary, className === "model-cell" ? "model-name" : undefined));
  if (secondary) {
    cell.append(makeElement("span", secondary, className === "model-cell" ? "model-source" : "cell-note"));
  }
  row.append(cell);
}

function addRow(entry) {
  const row = document.createElement("tr");
  addCell(row, `#${integer(entry.rank)}`, `submission ${entry.submission_id.slice(0, 12)}`);
  addCell(
    row,
    entry.model.display_name,
    `${entry.model.source} | ${entry.model.precision} | ${identityLabel(entry.model)}`,
    "model-cell",
  );
  addCell(row, entry.profile, `suite ${entry.suite_version}`);
  addHardwareCell(row, entry);
  addCell(
    row,
    percentage(entry.metrics.semantic_score_percent),
    `${integer(entry.metrics.semantic_pass_count)} of ${integer(entry.metrics.scored_case_count)} scored`,
  );
  addCell(
    row,
    percentage(entry.metrics.exact_format_score_percent),
    `${integer(entry.metrics.exact_format_pass_count)} of ${integer(entry.metrics.scored_case_count)} scored`,
  );
  addCell(
    row,
    entry.metrics.completion_tokens_per_second === null
      ? "--"
      : decimal(entry.metrics.completion_tokens_per_second),
    entry.metrics.completion_tokens_per_second === null
      ? "not fully reported"
      : `${integer(entry.metrics.usage_coverage_cases)} of ${integer(entry.metrics.case_count)} cases`,
  );
  addCell(row, `${decimal(entry.metrics.latency_ms_mean)} ms`, "observed mean");
  const seed = entry.settings.seed === null ? "none" : integer(entry.settings.seed);
  addCell(
    row,
    `T ${settingNumber(entry.settings.temperature)} | top-p ${settingNumber(entry.settings.top_p)}`,
    `max ${integer(entry.settings.max_output_tokens)} | seed ${seed}`,
  );
  elements.body.append(row);
}

function compareNullableDescending(left, right) {
  if (left === null && right === null) {
    return 0;
  }
  if (left === null) {
    return 1;
  }
  if (right === null) {
    return -1;
  }
  return right - left;
}

function sortedEntries(values, sort) {
  const result = [...values];
  result.sort((left, right) => {
    let comparison = 0;
    if (sort === "format") {
      comparison = right.metrics.exact_format_score_percent - left.metrics.exact_format_score_percent;
    } else if (sort === "throughput") {
      comparison = compareNullableDescending(
        left.metrics.completion_tokens_per_second,
        right.metrics.completion_tokens_per_second,
      );
    } else if (sort === "latency") {
      comparison = left.metrics.latency_ms_mean - right.metrics.latency_ms_mean;
    } else if (sort === "context") {
      comparison = right.model.declared_context_tokens - left.model.declared_context_tokens;
    } else {
      comparison = right.metrics.semantic_score_percent - left.metrics.semantic_score_percent;
    }
    if (comparison !== 0) {
      return comparison;
    }
    comparison = right.metrics.exact_format_score_percent - left.metrics.exact_format_score_percent;
    if (comparison !== 0) {
      return comparison;
    }
    return 0;
  });
  return result;
}

function showStatus(message) {
  elements.status.textContent = message;
  elements.status.hidden = false;
  elements.table.hidden = true;
}

function render() {
  const query = elements.search.value.trim().toLocaleLowerCase();
  const hardware = elements.hardwareFilter.value;
  const filtered = entries.filter((entry) => {
    const haystack = `${entry.model.display_name} ${entry.model.source}`.toLocaleLowerCase();
    const matchesHardware = hardware === "all" || hardwareCategories(entry).includes(hardware);
    return matchesHardware && (!query || haystack.includes(query));
  });
  const visible = sortedEntries(filtered, elements.sort.value);
  elements.updated.textContent =
    visible.length === entries.length
      ? `${integer(entries.length)} published result${entries.length === 1 ? "" : "s"}`
      : `${integer(visible.length)} of ${integer(entries.length)} results shown`;

  elements.body.replaceChildren();
  if (visible.length === 0) {
    showStatus(
      entries.length === 0
        ? "No reviewed benchmark results have been published yet."
        : "No published results match these filters.",
    );
    return;
  }

  visible.forEach(addRow);
  elements.status.hidden = true;
  elements.table.hidden = false;
}

function setSubmissionStatus(message, state) {
  elements.submissionStatus.textContent = message;
  elements.submissionStatus.classList.remove("submission-status-success", "submission-status-error");
  if (state === "success") {
    elements.submissionStatus.classList.add("submission-status-success");
  } else if (state === "error") {
    elements.submissionStatus.classList.add("submission-status-error");
  }
}

function clearCheckedSubmission(message, state = "error") {
  checkedSubmission = null;
  checkedSubmissionText = "";
  elements.copySubmission.disabled = true;
  elements.downloadSubmission.disabled = true;
  elements.continueSubmission.hidden = true;
  elements.submissionPreview.hidden = true;
  elements.previewProfile.textContent = "";
  elements.previewModel.textContent = "";
  elements.previewSuite.textContent = "";
  elements.previewHardware.textContent = "";
  setSubmissionStatus(message, state);
}

function showCheckedSubmission(submission, source) {
  checkedSubmission = submission;
  // Preserve the exact candidate bytes that the contributor reviewed locally.
  checkedSubmissionText = source;
  elements.previewProfile.textContent = submission.profile;
  elements.previewModel.textContent = submission.model.display_name;
  elements.previewSuite.textContent = submission.suite_version;
  const acceleratorPreview =
    submission.hardware.accelerators.length && submission.hardware.execution_mode !== "cpu_only"
    ? acceleratorSummary(submission.hardware)
    : "No accelerator used";
  elements.previewHardware.textContent = `CPU: ${submission.hardware.cpu.model} | ${acceleratorPreview} | ${decimal(
    submission.hardware.memory.system_gb,
  )} GB | ${submission.runtime.name} ${submission.runtime.version}`;
  elements.submissionPreview.hidden = false;
  elements.copySubmission.disabled = false;
  elements.downloadSubmission.disabled = false;
  elements.continueSubmission.hidden = false;
  setSubmissionStatus(
    "The closed public shape looks right. This convenience check does not replace CLI and CI privacy checks, content-hash validation, or maintainer review.",
    "success",
  );
}

async function checkSubmissionFile() {
  const [file] = elements.submissionFile.files;
  if (!file) {
    clearCheckedSubmission("No file selected.", "neutral");
    return;
  }
  if (!file.name.toLocaleLowerCase().endsWith(".json")) {
    clearCheckedSubmission("Choose the minimized JSON file created by the test bench.");
    return;
  }
  if (file.size === 0 || file.size > MAX_SUBMISSION_BYTES) {
    clearCheckedSubmission("The file must be a non-empty JSON document no larger than 256 KB.");
    return;
  }

  setSubmissionStatus("Checking the file locally...", "neutral");
  try {
    const source = await file.text();
    if (elements.submissionFile.files[0] !== file) {
      return;
    }
    if (new TextEncoder().encode(source).byteLength > MAX_SUBMISSION_BYTES) {
      throw new Error("Submission data is larger than expected.");
    }
    showCheckedSubmission(validateSubmission(JSON.parse(source)), source);
  } catch (error) {
    clearCheckedSubmission(
      "This is not a valid minimized submission. Raw run reports and extra fields are not accepted.",
    );
  }
}

async function copyCheckedSubmission() {
  if (!checkedSubmissionText) {
    return;
  }
  try {
    await navigator.clipboard.writeText(checkedSubmissionText);
    setSubmissionStatus("Checked JSON copied. The file has not been uploaded.", "success");
  } catch (error) {
    setSubmissionStatus("Copying is unavailable in this browser. Download the checked copy instead.", "error");
  }
}

function downloadCheckedSubmission() {
  if (!checkedSubmission || !checkedSubmissionText) {
    return;
  }
  const blob = new Blob([checkedSubmissionText], { type: "application/json" });
  const downloadUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = downloadUrl;
  link.download = `${checkedSubmission.submission_id}.json`;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
  setSubmissionStatus("Checked copy downloaded. The file has not been uploaded.", "success");
}

async function loadLeaderboard() {
  try {
    const response = await fetch(DATA_URL, { cache: "no-cache", credentials: "omit" });
    if (!response.ok) {
      throw new Error("Leaderboard data is unavailable.");
    }
    const contentLength = Number(response.headers.get("content-length"));
    if (Number.isFinite(contentLength) && contentLength > MAX_DATA_BYTES) {
      throw new Error("Leaderboard data is larger than expected.");
    }
    const source = await response.text();
    if (new TextEncoder().encode(source).byteLength > MAX_DATA_BYTES) {
      throw new Error("Leaderboard data is larger than expected.");
    }
    const payload = validatePayload(JSON.parse(source));
    entries = payload.entries;
    populateHardwareFilter(entries);
    render();
  } catch (error) {
    elements.updated.textContent = "Leaderboard unavailable";
    showStatus("The leaderboard could not be loaded. Try again later or view the repository for current results.");
  }
}

elements.search.addEventListener("input", render);
elements.hardwareFilter.addEventListener("change", render);
elements.sort.addEventListener("change", render);
elements.filters.addEventListener("submit", (event) => event.preventDefault());
elements.submissionFile.addEventListener("change", checkSubmissionFile);
elements.copySubmission.addEventListener("click", copyCheckedSubmission);
elements.downloadSubmission.addEventListener("click", downloadCheckedSubmission);

loadLeaderboard();
