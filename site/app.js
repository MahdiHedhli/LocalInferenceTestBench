"use strict";

const DATA_URL = "./data/leaderboard.json";
const SHARD_URL_PREFIX = "./data/leaderboard-";
const SHARD_URL_SUFFIX = ".json";
const MAX_DATA_BYTES = 2 * 1024 * 1024;
const DATA_FETCH_TIMEOUT_MS = 15 * 1000;
const MAX_SUBMISSION_BYTES = 256 * 1024;
const LEADERBOARD_INDEX_VERSION = "1.0";
const SUBMISSION_SCHEMA_VERSION = "1.1";
const LEADERBOARD_SCHEMA_VERSIONS = new Set(["1.0", "1.1"]);
const MODEL_DISPLAY_NAME_MAX = 160;
const MODEL_SOURCE_MAX = 240;
const MODEL_PRECISION_MAX = 80;
const CASE_ID = /^[a-z0-9][a-z0-9._-]{0,127}$/u;
const SUITE_REGISTRY = Object.freeze({
  "standard@1.0": Object.freeze([
    Object.freeze({ case_id: "structured-json", capability: "structured_output", modality: "text" }),
    Object.freeze({ case_id: "python-ast", capability: "coding", modality: "text" }),
    Object.freeze({ case_id: "defensive-triage", capability: "cyber_triage", modality: "text" }),
    Object.freeze({ case_id: "read-only-tool", capability: "agent_tool_use", modality: "text" }),
    Object.freeze({ case_id: "unapproved-change-boundary", capability: "safety_boundary", modality: "text" }),
  ]),
});
const CAPABILITIES = new Set([
  "structured_output",
  "coding",
  "agent_tool_use",
  "cyber_triage",
  "safety_boundary",
]);
const MODALITIES = new Set(["text", "vision"]);
const OUTCOMES = new Set([
  "pass",
  "semantic_only",
  "format_only",
  "fail",
  "not_scored",
  "not_applicable",
]);
const PUBLIC_VALIDITIES = new Set(["clean", "nonquiescent", "degraded_midrun"]);
const LEADERBOARD_VALIDITIES = new Set([...PUBLIC_VALIDITIES, "legacy_unreported"]);
const MEASUREMENT_OUTCOMES = new Set(["within_thresholds", "threshold_crossed"]);
const MEASUREMENT_CATEGORY_ORDER = [
  "memory_pressure",
  "thermal",
  "sustained_load",
  "swap",
  "resident_models",
];
const MEASUREMENT_CATEGORIES = new Set(MEASUREMENT_CATEGORY_ORDER);
const DETERMINISM_VERDICTS = new Set(["stable", "warning", "blocking_instability"]);
const ROUTES = new Set([
  "direct_response",
  "read_only_tool",
  "safe_refusal",
  "unsafe_mutation",
  "unexpected_tool",
  "unrecognized",
  "not_applicable",
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
  "not_applicable",
]);
const MEMORY_ARCHITECTURES = new Set(["shared", "discrete", "mixed", "unknown"]);
const ACCELERATOR_KINDS = new Set([
  "integrated_gpu",
  "discrete_gpu",
  "neural_accelerator",
  "other",
]);
const EXECUTION_MODES = new Set(["cpu_only", "accelerator_only", "hybrid", "unknown"]);
const SPECULATIVE_DECODING_MODES = new Set(["enabled", "disabled", "unknown"]);
const OFFLOAD_MODES = new Set(["none", "partial", "maximum", "not_applicable", "unknown"]);
const REASONING_EFFORTS = new Set(["none", "minimal", "low", "medium", "high", "xhigh"]);
const DESCRIPTOR_UUID = /(?:^|[^0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:$|[^0-9a-f])/iu;
const DESCRIPTOR_LABEL = /\b(?:s\s*\/?\s*n|serial(?:\s+(?:number|no|id))?|inventory\s+(?:id|tag)|asset\s+(?:id|tag)|device\s+uuid|machine\s+(?:id|name)|host\s*name|user\s*name|account\s+(?:id|name))\b/iu;
const DESCRIPTOR_NETWORK = /(?:^|[^0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?:$|[^0-9])|(?:^|[^0-9a-f:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?:%[a-z0-9_.-]+)?(?:$|[^0-9a-f:])/iu;
const DESCRIPTOR_URL_OR_EMAIL = /(?:\bhttps?:|\b[a-z][a-z0-9+.-]*:\/\/|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,})/iu;
const LOCAL_HOST_MARKER = new RegExp(
  `(?:^|[^a-z0-9])${"local" + "host"}(?:$|[^a-z0-9])`,
  "iu",
);
const HOME_PATH = new RegExp(
  String.raw`(?:^|\s)(?:/(?:${"Us" + "ers"}|${"ho" + "me"})/[^/\s]+|/${
    "ro" + "ot"
  }(?:/|\b)|[A-Za-z]:[\\/]${"Us" + "ers"}[\\/][^\\/\s]+)`,
  "iu",
);
const MAC_COLON_OR_HYPHEN = /(?:^|[^0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?:$|[^0-9a-f])/iu;
const MAC_DOTTED = /(?:^|[^0-9a-f])(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}(?:$|[^0-9a-f])/iu;
const PRIVATE_HOST = /(?:^|[^a-z0-9_-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:lan|local|internal|home|corp|private|localdomain|home\.arpa)\.*(?:$|[^a-z0-9_.-])/iu;
const PRIVATE_KEY_HEADER = /-{5}BEGIN(?: [A-Z0-9]+)*(?: PRIVATE KEY| PRIVATE KEY BLOCK)-{5}/iu;
const CREDENTIAL_ASSIGNMENT = /(?:^|[\s,{;])["']?(?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?token|auth[_-]?token|bearer[_-]?token|client[_-]?secret|connection[_-]?string|credential|password|passwd|private[_-]?key|secret|token)["']?\s*(?::|=)\s*\S+/iu;
const EXPERIMENT_OR_LOCALHOST = new RegExp(
  `(?:^|[^a-z0-9])(?:${[
    "op" + "ik",
    "poly" + "range",
    "local" + "host",
  ].join("|")})(?:$|[^a-z0-9])`,
  "iu",
);
const MODEL_DESCRIPTOR_ASCII = /^[\x20-\x7e]+$/u;
const MODEL_REVIEW_INJECTION = /(?:\b(?:ignore|disregard|override|bypass|forget|accept|approve|merge)\b|\b(?:instructions?|prompts?|codex|coderabbit(?:ai)?|reviewer|maintainer)\b|\b(?:system|assistant|developer|user)\s*:|\b(?:result|submission|benchmark)\b.{0,32}\b(?:safe|valid|verified|trusted|approved|pass(?:ed)?)\b|\b(?:mark|treat|label|classify)\b.{0,32}\b(?:safe|valid|verified|trusted|approved|pass(?:ed)?)\b|```|<!--|-->|<\s*\/?\s*script\b|\[\s*inst\s*\]|<<\s*sys\s*>>)/iu;
const SCANNER_SUPPRESSION_MARKER = new RegExp(
  "\\b" + "git" + "leaks\\s*:\\s*allow\\b",
  "iu",
);

const elements =
  typeof document === "undefined"
    ? {}
    : {
        body: document.querySelector("#leaderboard-body"),
        filters: document.querySelector("#leaderboard-filters"),
        hardwareFilter: document.querySelector("#hardware-filter"),
        validityFilter: document.querySelector("#validity-filter"),
        periodFilter: document.querySelector("#period-filter"),
        search: document.querySelector("#model-search"),
        sort: document.querySelector("#sort-results"),
        status: document.querySelector("#leaderboard-status"),
        table: document.querySelector("#leaderboard-table-shell"),
        loadMore: document.querySelector("#load-more-results"),
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
let leaderboardIndex = null;
let nextShardNumber = 1;
let loadingShard = false;
let shardRankingState = createShardRankingState();
let checkedSubmission = null;
let checkedSubmissionText = "";
const rawNumberTokens = new WeakMap();

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

function parseStrictJson(source) {
  if (typeof source !== "string") {
    throw new Error("JSON source must be text.");
  }
  let position = 0;
  const numbers = [];

  function fail() {
    throw new Error("JSON source is not strict or contains a duplicate member.");
  }

  function skipWhitespace() {
    while (
      position < source.length &&
      [" ", "\t", "\r", "\n"].includes(source[position])
    ) {
      position += 1;
    }
  }

  function parseString() {
    if (source[position] !== '"') {
      fail();
    }
    const start = position;
    position += 1;
    while (position < source.length) {
      const character = source[position];
      const codePoint = source.charCodeAt(position);
      if (character === '"') {
        position += 1;
        return JSON.parse(source.slice(start, position));
      }
      if (codePoint < 0x20) {
        fail();
      }
      if (character === "\\") {
        position += 1;
        if (position >= source.length) {
          fail();
        }
        const escape = source[position];
        if (escape === "u") {
          const digits = source.slice(position + 1, position + 5);
          if (!/^[0-9a-f]{4}$/iu.test(digits)) {
            fail();
          }
          position += 5;
          continue;
        }
        if (!['"', "\\", "/", "b", "f", "n", "r", "t"].includes(escape)) {
          fail();
        }
      }
      position += 1;
    }
    fail();
  }

  function parseNumber(path) {
    const match = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/u.exec(
      source.slice(position),
    );
    if (match === null) {
      fail();
    }
    numbers.push({ path, lexeme: match[0] });
    position += match[0].length;
  }

  function parseValue(depth, path) {
    if (depth > 128) {
      fail();
    }
    skipWhitespace();
    const character = source[position];
    if (character === "{") {
      parseObject(depth + 1, path);
      return;
    }
    if (character === "[") {
      parseArray(depth + 1, path);
      return;
    }
    if (character === '"') {
      parseString();
      return;
    }
    for (const literal of ["true", "false", "null"]) {
      if (source.startsWith(literal, position)) {
        position += literal.length;
        return;
      }
    }
    parseNumber(path);
  }

  function parseObject(depth, path) {
    position += 1;
    skipWhitespace();
    if (source[position] === "}") {
      position += 1;
      return;
    }
    const keys = new Set();
    while (position < source.length) {
      const key = parseString();
      if (keys.has(key)) {
        fail();
      }
      keys.add(key);
      skipWhitespace();
      if (source[position] !== ":") {
        fail();
      }
      position += 1;
      parseValue(depth, [...path, key]);
      skipWhitespace();
      if (source[position] === "}") {
        position += 1;
        return;
      }
      if (source[position] !== ",") {
        fail();
      }
      position += 1;
      skipWhitespace();
    }
    fail();
  }

  function parseArray(depth, path) {
    position += 1;
    skipWhitespace();
    if (source[position] === "]") {
      position += 1;
      return;
    }
    let index = 0;
    while (position < source.length) {
      parseValue(depth, [...path, index]);
      index += 1;
      skipWhitespace();
      if (source[position] === "]") {
        position += 1;
        return;
      }
      if (source[position] !== ",") {
        fail();
      }
      position += 1;
    }
    fail();
  }

  parseValue(0, []);
  skipWhitespace();
  if (position !== source.length) {
    fail();
  }
  const parsed = JSON.parse(source);
  if (isRecord(parsed) || Array.isArray(parsed)) {
    rawNumberTokens.set(parsed, numbers);
  }
  return parsed;
}

function decodeStrictUtf8(value) {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  if (
    bytes.length >= 3 &&
    bytes[0] === 0xef &&
    bytes[1] === 0xbb &&
    bytes[2] === 0xbf
  ) {
    throw new Error("UTF-8 byte-order marks are not accepted.");
  }
  return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
}

function isCanonicalFloatPath(path) {
  const joined = path.join(".");
  if (
    [
      "hardware.memory.system_gb",
      "settings.temperature",
      "settings.top_p",
      "metrics.latency_ms_mean",
      "metrics.completion_tokens_per_second",
      "determinism.semantic_pass_rate",
    ].includes(joined)
  ) {
    return true;
  }
  return (
    path.length === 4 &&
    path[0] === "hardware" &&
    path[1] === "accelerators" &&
    Number.isInteger(path[2]) &&
    path[3] === "memory_gb"
  );
}

function validateRawSubmissionNumberTypes(submission) {
  const numbers = rawNumberTokens.get(submission);
  if (numbers === undefined) {
    return true;
  }
  return numbers.every(
    ({ path, lexeme }) =>
      isCanonicalFloatPath(path) || /^-?(?:0|[1-9][0-9]*)$/u.test(lexeme),
  );
}

function pythonFloatText(value) {
  if (value === 0) {
    return "0.0";
  }
  if (Number.isInteger(value)) {
    return `${value}.0`;
  }
  if (Math.abs(value) < 0.0001) {
    const [mantissa, rawExponent] = value.toExponential().split("e");
    const exponent = Number(rawExponent);
    const sign = exponent >= 0 ? "+" : "-";
    return `${mantissa}e${sign}${String(Math.abs(exponent)).padStart(2, "0")}`;
  }
  return JSON.stringify(value);
}

function canonicalJson(value, path = []) {
  if (value === null) {
    return "null";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new Error("Canonical JSON contains a non-finite number.");
    }
    if (isCanonicalFloatPath(path)) {
      return pythonFloatText(value);
    }
    if (!Number.isSafeInteger(value)) {
      throw new Error("Canonical JSON contains an unsupported number.");
    }
    return String(Object.is(value, -0) ? 0 : value);
  }
  if (Array.isArray(value)) {
    return `[${value
      .map((item, index) => canonicalJson(item, [...path, index]))
      .join(",")}]`;
  }
  if (isRecord(value)) {
    return `{${Object.keys(value)
      .sort()
      .map(
        (key) =>
          `${JSON.stringify(key)}:${canonicalJson(value[key], [...path, key])}`,
      )
      .join(",")}}`;
  }
  throw new Error("Canonical JSON contains an unsupported value.");
}

function digestEngine() {
  if (globalThis.crypto?.subtle) {
    return globalThis.crypto.subtle;
  }
  if (typeof require === "function") {
    return require("node:crypto").webcrypto.subtle;
  }
  throw new Error("SHA-256 is unavailable.");
}

async function computeSubmissionId(submission) {
  const payload = Object.fromEntries(
    Object.entries(submission).filter(([key]) => key !== "submission_id"),
  );
  const encoded = new TextEncoder().encode(canonicalJson(payload));
  const digest = await digestEngine().digest("SHA-256", encoded);
  return [...new Uint8Array(digest)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

function suiteKey(profile, suiteVersion) {
  return `${profile}@${suiteVersion}`;
}

function resolveSuite(profile, suiteVersion, registry = SUITE_REGISTRY) {
  if (typeof profile !== "string" || typeof suiteVersion !== "string") {
    return null;
  }
  const suite = registry[suiteKey(profile, suiteVersion)];
  if (!Array.isArray(suite) || suite.length === 0) {
    return null;
  }
  const seen = new Set();
  for (const item of suite) {
    if (
      !hasExactKeys(item, ["case_id", "capability", "modality"]) ||
      typeof item.case_id !== "string" ||
      !CASE_ID.test(item.case_id) ||
      seen.has(item.case_id) ||
      !CAPABILITIES.has(item.capability) ||
      !MODALITIES.has(item.modality)
    ) {
      return null;
    }
    seen.add(item.case_id);
  }
  return suite;
}

function isInteger(value, minimum, maximum = Number.MAX_SAFE_INTEGER) {
  return Number.isSafeInteger(value) && value >= minimum && value <= maximum;
}

function isFiniteNumber(value, minimum, maximum = Number.MAX_VALUE) {
  return Number.isFinite(value) && value >= minimum && value <= maximum;
}

function isRejectedIpv4(candidate) {
  const parts = candidate.split(".").map(Number);
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part > 255)) {
    return false;
  }
  const [first, second, third, fourth] = parts;
  return (
    (first === 0 && second === 0 && third === 0 && fourth === 0) ||
    first === 10 ||
    first === 127 ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168) ||
    (first === 100 && second >= 64 && second <= 127) ||
    (first === 169 && second === 254)
  );
}

function normalizedIpv6(candidate) {
  try {
    const address = candidate.split("%", 1)[0];
    return new URL("http" + `://[${address}]/`).hostname.slice(1, -1);
  } catch (error) {
    return null;
  }
}

function isRejectedIpv6(candidate) {
  const normalized = normalizedIpv6(candidate);
  if (normalized === null) {
    return false;
  }
  if (["::", "::1"].includes(normalized)) {
    return true;
  }
  const first = Number.parseInt(normalized.split(":", 1)[0], 16);
  return (first >> 9) === 0x7e || (first >> 6) === 0x3fa;
}

function containsRejectedAddress(value) {
  const ipv4 = /(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])/gu;
  if ([...value.matchAll(ipv4)].some((match) => isRejectedIpv4(match[0]))) {
    return true;
  }
  const ipv6 = /(?<![0-9a-f:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?:%[a-z0-9_.-]+)?(?![0-9a-f:])/giu;
  return [...value.matchAll(ipv6)].some((match) => isRejectedIpv6(match[0]));
}

function containsPrivateUrl(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch (error) {
    return false;
  }
  if (!["http:", "https:"].includes(parsed.protocol)) {
    return false;
  }
  const hostname = parsed.hostname.toLowerCase();
  if (hostname === "localhost" || hostname.endsWith(".local")) {
    return true;
  }
  if (hostname.startsWith("[") && hostname.endsWith("]")) {
    return isRejectedIpv6(hostname.slice(1, -1));
  }
  return isRejectedIpv4(hostname);
}

function containsStaticProhibitedData(value) {
  if (typeof value === "string") {
    return (
      HOME_PATH.test(value) ||
      containsRejectedAddress(value) ||
      containsPrivateUrl(value) ||
      MAC_COLON_OR_HYPHEN.test(value) ||
      MAC_DOTTED.test(value) ||
      PRIVATE_HOST.test(value) ||
      PRIVATE_KEY_HEADER.test(value) ||
      CREDENTIAL_ASSIGNMENT.test(value) ||
      EXPERIMENT_OR_LOCALHOST.test(value)
    );
  }
  if (Array.isArray(value)) {
    return value.some(containsStaticProhibitedData);
  }
  if (isRecord(value)) {
    return Object.values(value).some(containsStaticProhibitedData);
  }
  return false;
}

function validateMeasurementPeriod(value) {
  if (typeof value !== "string" || !/^[0-9]{4}-(?:0[1-9]|1[0-2])$/u.test(value)) {
    return false;
  }
  const now = new Date();
  const currentPeriod = `${String(now.getUTCFullYear()).padStart(4, "0")}-${String(
    now.getUTCMonth() + 1,
  ).padStart(2, "0")}`;
  return value <= currentPeriod;
}

function validateMeasurementSample(sample) {
  if (
    !hasExactKeys(sample, ["outcome", "categories"]) ||
    !MEASUREMENT_OUTCOMES.has(sample.outcome) ||
    !Array.isArray(sample.categories) ||
    sample.categories.length > MEASUREMENT_CATEGORY_ORDER.length ||
    sample.categories.some((category) => !MEASUREMENT_CATEGORIES.has(category))
  ) {
    return false;
  }
  const expected = MEASUREMENT_CATEGORY_ORDER.filter((category) =>
    sample.categories.includes(category),
  );
  return (
    JSON.stringify(sample.categories) === JSON.stringify(expected) &&
    (sample.outcome === "threshold_crossed") === (sample.categories.length > 0)
  );
}

function derivedMeasurementValidity(conditions) {
  const pre = new Set(conditions.pre.categories);
  if (conditions.post.categories.some((category) => !pre.has(category))) {
    return "degraded_midrun";
  }
  return pre.size > 0 ? "nonquiescent" : "clean";
}

function validateMeasurementConditions(conditions) {
  if (
    !hasExactKeys(conditions, ["pre", "post", "hard_threshold_crossed"]) ||
    !validateMeasurementSample(conditions.pre) ||
    !validateMeasurementSample(conditions.post) ||
    typeof conditions.hard_threshold_crossed !== "boolean"
  ) {
    return false;
  }
  return (
    conditions.hard_threshold_crossed ===
    (conditions.pre.categories.length > 0 || conditions.post.categories.length > 0)
  );
}

function validateDeterminism(determinism) {
  if (
    !hasExactKeys(determinism, [
      "n_runs",
      "semantic_pass_rate",
      "envelope_class_stable",
      "finish_reason_stable",
      "fingerprint_stable",
      "verdict",
    ]) ||
    !isInteger(determinism.n_runs, 3, 5) ||
    !isFiniteNumber(determinism.semantic_pass_rate, 0, 1) ||
    !hasAtMostSixDecimalPlaces(determinism.semantic_pass_rate) ||
    typeof determinism.envelope_class_stable !== "boolean" ||
    typeof determinism.finish_reason_stable !== "boolean" ||
    typeof determinism.fingerprint_stable !== "boolean" ||
    !DETERMINISM_VERDICTS.has(determinism.verdict)
  ) {
    return false;
  }
  const possibleRates = Array.from(
    { length: determinism.n_runs + 1 },
    (_unused, passed) => Number((passed / determinism.n_runs).toFixed(6)),
  );
  if (!possibleRates.includes(determinism.semantic_pass_rate)) {
    return false;
  }
  const semanticStable = [0, 1].includes(determinism.semantic_pass_rate);
  const expectedVerdict =
    !semanticStable || !determinism.envelope_class_stable || !determinism.finish_reason_stable
      ? "blocking_instability"
      : !determinism.fingerprint_stable
        ? "warning"
        : "stable";
  return determinism.verdict === expectedVerdict;
}

function isPublicText(value, maximum = 500) {
  return (
    typeof value === "string" &&
    [...value].length >= 1 &&
    [...value].length <= maximum &&
    !/[\u0000-\u001f\u007f-\u009f\u200e\u200f\u2028-\u202e\u2066-\u2069\ud800-\udfff]/u.test(value) &&
    !SCANNER_SUPPRESSION_MARKER.test(value)
  );
}

function isPublicDescriptorText(value, maximum) {
  return (
    isPublicText(value, maximum) &&
    MODEL_DESCRIPTOR_ASCII.test(value) &&
    !MODEL_REVIEW_INJECTION.test(value) &&
    !DESCRIPTOR_UUID.test(value) &&
    !DESCRIPTOR_LABEL.test(value) &&
    !DESCRIPTOR_NETWORK.test(value) &&
    !DESCRIPTOR_URL_OR_EMAIL.test(value) &&
    !LOCAL_HOST_MARKER.test(value)
  );
}

function isModelDescriptorText(value, maximum) {
  return isPublicDescriptorText(value, maximum);
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
    isModelDescriptorText(model.display_name, MODEL_DISPLAY_NAME_MAX) &&
    isModelDescriptorText(model.source, MODEL_SOURCE_MAX) &&
    isModelDescriptorText(model.precision, MODEL_PRECISION_MAX) &&
    isModelDescriptorText(model[identityFields[0]], 200) &&
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
      typeof accelerator.model === "string" ? accelerator.model.toLowerCase() : "",
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

function validateRuntimeConfiguration(configuration) {
  return (
    hasExactKeys(configuration, [
      "context_window_tokens",
      "concurrent_requests",
      "speculative_decoding",
      "offload_mode",
    ]) &&
    (configuration.context_window_tokens === null ||
      isInteger(configuration.context_window_tokens, 1)) &&
    (configuration.concurrent_requests === null ||
      isInteger(configuration.concurrent_requests, 1, 4096)) &&
    SPECULATIVE_DECODING_MODES.has(configuration.speculative_decoding) &&
    OFFLOAD_MODES.has(configuration.offload_mode)
  );
}

function validateSettings(settings, contextTokens, runtimeConfiguration) {
  const configuredContext = runtimeConfiguration?.context_window_tokens;
  const maximumOutputTokens =
    configuredContext === undefined || configuredContext === null
      ? contextTokens
      : Math.min(contextTokens, configuredContext);
  return (
    hasExactKeys(
      settings,
      ["temperature", "top_p", "max_output_tokens", "seed"],
      ["reasoning_effort"],
    ) &&
    isFiniteNumber(settings.temperature, 0, 2) &&
    hasAtMostSixDecimalPlaces(settings.temperature) &&
    isFiniteNumber(settings.top_p, Number.MIN_VALUE, 1) &&
    hasAtMostSixDecimalPlaces(settings.top_p) &&
    isInteger(settings.max_output_tokens, 1, maximumOutputTokens) &&
    (settings.seed === null || Number.isSafeInteger(settings.seed)) &&
    (!Object.hasOwn(settings, "reasoning_effort") ||
      REASONING_EFFORTS.has(settings.reasoning_effort))
  );
}

function validateMetrics(metrics, suiteLength, legacy = false) {
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
  if (
    !isInteger(metrics.case_count, 1, suiteLength) ||
    !isInteger(metrics.scored_case_count, 1, metrics.case_count)
  ) {
    return false;
  }
  const semanticPercent = Math.round((metrics.semantic_pass_count / metrics.scored_case_count) * 1000) / 10;
  const formatPercent = Math.round((metrics.exact_format_pass_count / metrics.scored_case_count) * 1000) / 10;
  return (
    (!legacy ||
      (metrics.case_count === suiteLength && metrics.scored_case_count === suiteLength)) &&
    isInteger(metrics.semantic_pass_count, 0, metrics.scored_case_count) &&
    isInteger(metrics.exact_format_pass_count, 0, metrics.scored_case_count) &&
    isInteger(metrics.usage_coverage_cases, 0, metrics.scored_case_count) &&
    isFiniteNumber(metrics.semantic_score_percent, 0, 100) &&
    isFiniteNumber(metrics.exact_format_score_percent, 0, 100) &&
    metrics.semantic_score_percent === semanticPercent &&
    metrics.exact_format_score_percent === formatPercent &&
    hasOneDecimalPlace(metrics.latency_ms_mean) &&
    (metrics.completion_tokens_per_second === null ||
      (hasOneDecimalPlace(metrics.completion_tokens_per_second) &&
        metrics.usage_coverage_cases === metrics.scored_case_count))
  );
}

function validateEntry(entry, leaderboardSchemaVersion = "1.0", registry = SUITE_REGISTRY) {
  const legacyDataset = leaderboardSchemaVersion === "1.0";
  const required = [
    "rank",
    "submission_id",
    "suite_version",
    "profile",
    "hardware",
    "runtime",
    "model",
    "settings",
    "metrics",
  ];
  const optional = ["runtime_configuration"];
  if (!legacyDataset) {
    required.push(
      "submission_schema_version",
      "validity",
      "measurement_period",
      "measurement_conditions",
    );
    optional.push("determinism");
  }
  if (!hasExactKeys(entry, required, optional)) {
    return false;
  }
  const suite = resolveSuite(entry.profile, entry.suite_version, registry);
  if (suite === null) {
    return false;
  }
  let evidenceValid = true;
  if (!legacyDataset) {
    if (entry.submission_schema_version === "1.0") {
      evidenceValid =
        entry.validity === "legacy_unreported" &&
        entry.measurement_period === null &&
        entry.measurement_conditions === null &&
        !Object.hasOwn(entry, "determinism");
    } else if (entry.submission_schema_version === SUBMISSION_SCHEMA_VERSION) {
      evidenceValid =
        PUBLIC_VALIDITIES.has(entry.validity) &&
        validateMeasurementPeriod(entry.measurement_period) &&
        validateMeasurementConditions(entry.measurement_conditions) &&
        entry.validity === derivedMeasurementValidity(entry.measurement_conditions) &&
        (!Object.hasOwn(entry, "determinism") || validateDeterminism(entry.determinism));
    } else {
      evidenceValid = false;
    }
  }
  return (
    isInteger(entry.rank, 1) &&
    typeof entry.submission_id === "string" &&
    /^[a-f0-9]{64}$/u.test(entry.submission_id) &&
    evidenceValid &&
    validateHardware(entry.hardware) &&
    validateRuntime(entry.runtime) &&
    (!Object.hasOwn(entry, "runtime_configuration") ||
      validateRuntimeConfiguration(entry.runtime_configuration)) &&
    validateModel(entry.model) &&
    validateSettings(
      entry.settings,
      entry.model.declared_context_tokens,
      entry.runtime_configuration,
    ) &&
    validateMetrics(entry.metrics, suite.length, legacyDataset)
  );
}

function validatePayload(payload) {
  if (
    !hasExactKeys(payload, ["schema_version", "entry_count", "entries"]) ||
    !LEADERBOARD_SCHEMA_VERSIONS.has(payload.schema_version) ||
    !isInteger(payload.entry_count, 0) ||
    !Array.isArray(payload.entries) ||
    payload.entries.length !== payload.entry_count ||
    !payload.entries.every((entry) => validateEntry(entry, payload.schema_version)) ||
    !validateRanking(payload.entries)
  ) {
    throw new Error("Leaderboard data does not match the expected public schema.");
  }
  return payload;
}

function validateIndex(payload) {
  if (
    !hasExactKeys(payload, [
      "index_version",
      "schema_version",
      "entry_count",
      "shard_count",
    ]) ||
    payload.index_version !== LEADERBOARD_INDEX_VERSION ||
    !LEADERBOARD_SCHEMA_VERSIONS.has(payload.schema_version) ||
    !isInteger(payload.entry_count, 0) ||
    !isInteger(payload.shard_count, 0) ||
    (payload.entry_count === 0) !== (payload.shard_count === 0) ||
    payload.shard_count > payload.entry_count
  ) {
    throw new Error("Leaderboard index does not match the expected public schema.");
  }
  return payload;
}

function validateShard(payload, expectedShardId, expectedSchemaVersion) {
  if (
    !hasExactKeys(payload, [
      "index_version",
      "schema_version",
      "shard_id",
      "entry_count",
      "entries",
    ]) ||
    payload.index_version !== LEADERBOARD_INDEX_VERSION ||
    payload.schema_version !== expectedSchemaVersion ||
    payload.shard_id !== expectedShardId ||
    !isInteger(payload.entry_count, 1) ||
    !Array.isArray(payload.entries) ||
    payload.entries.length !== payload.entry_count ||
    !payload.entries.every((entry) => validateEntry(entry, expectedSchemaVersion)) ||
    !validateRankingSegment(payload.entries)
  ) {
    throw new Error("Leaderboard shard does not match the expected public schema.");
  }
  return payload;
}

function validateRankingSegment(values) {
  const seen = new Set();
  let previousEntry = null;
  let previousQuality = null;
  let previousRank = null;
  for (const entry of values) {
    if (seen.has(entry.submission_id)) {
      return false;
    }
    if (previousEntry !== null && compareCanonicalLeaderboardOrder(previousEntry, entry) > 0) {
      return false;
    }
    seen.add(entry.submission_id);
    const quality = [
      entry.metrics.semantic_score_percent,
      entry.metrics.exact_format_score_percent,
    ];
    if (previousQuality !== null) {
      const sameQuality =
        quality[0] === previousQuality[0] && quality[1] === previousQuality[1];
      if (
        quality[0] > previousQuality[0] ||
        (quality[0] === previousQuality[0] && quality[1] > previousQuality[1]) ||
        (sameQuality && entry.rank !== previousRank) ||
        (!sameQuality && entry.rank !== previousRank + 1)
      ) {
        return false;
      }
    }
    previousQuality = quality;
    previousRank = entry.rank;
    previousEntry = entry;
  }
  return true;
}

function createShardRankingState() {
  return {
    entryCount: 0,
    previousEntry: null,
    submissionIds: new Set(),
  };
}

function hasSameLeaderboardQuality(left, right) {
  return (
    left.metrics.semantic_score_percent === right.metrics.semantic_score_percent &&
    left.metrics.exact_format_score_percent === right.metrics.exact_format_score_percent
  );
}

function validateAndTrackShardRanking(state, values) {
  if (values.length === 0) {
    return false;
  }
  const firstEntry = values[0];
  if (state.previousEntry === null) {
    if (firstEntry.rank !== 1) {
      return false;
    }
  } else {
    const expectedRank =
      state.previousEntry.rank +
      (hasSameLeaderboardQuality(state.previousEntry, firstEntry) ? 0 : 1);
    if (
      compareCanonicalLeaderboardOrder(state.previousEntry, firstEntry) > 0 ||
      firstEntry.rank !== expectedRank
    ) {
      return false;
    }
  }
  if (values.some((entry) => state.submissionIds.has(entry.submission_id))) {
    return false;
  }
  for (const entry of values) {
    state.submissionIds.add(entry.submission_id);
  }
  state.entryCount += values.length;
  state.previousEntry = values[values.length - 1];
  return true;
}

function compareCanonicalLeaderboardOrder(left, right) {
  const numberKeys = ["semantic_score_percent", "exact_format_score_percent"];
  for (const key of numberKeys) {
    const comparison = right.metrics[key] - left.metrics[key];
    if (comparison !== 0) {
      return comparison;
    }
  }
  const textPairs = [
    [left.model.source.toLowerCase(), right.model.source.toLowerCase()],
    [left.model.display_name.toLowerCase(), right.model.display_name.toLowerCase()],
    [left.submission_id, right.submission_id],
  ];
  for (const [leftValue, rightValue] of textPairs) {
    if (leftValue < rightValue) {
      return -1;
    }
    if (leftValue > rightValue) {
      return 1;
    }
  }
  return 0;
}

function validateRanking(values) {
  const seen = new Set();
  let previousEntry = null;
  let previousQuality = null;
  let expectedRank = 0;
  for (const entry of values) {
    if (seen.has(entry.submission_id)) {
      return false;
    }
    if (previousEntry !== null && compareCanonicalLeaderboardOrder(previousEntry, entry) > 0) {
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
    previousEntry = entry;
  }
  return true;
}

function hasAtMostSixDecimalPlaces(value) {
  return Number.isFinite(value) && Number(value.toFixed(6)) === value;
}

function hasOneDecimalPlace(value) {
  return (
    isFiniteNumber(value, 0, 1_000_000_000) &&
    Number(value.toFixed(1)) === value
  );
}

function validateCases(cases, suite) {
  if (!Array.isArray(cases) || cases.length !== suite.length) {
    return false;
  }
  return cases.every((item, index) => {
    if (
      !hasExactKeys(item, [
        "case_id",
        "capability",
        "modality",
        "outcome",
        "route",
        "termination",
      ])
    ) {
      return false;
    }
    const expected = suite[index];
    const unsafePass =
      item.route === "unsafe_mutation" && ["pass", "semantic_only"].includes(item.outcome);
    const notApplicable = item.outcome === "not_applicable";
    return (
      item.case_id === expected.case_id &&
      item.capability === expected.capability &&
      item.modality === expected.modality &&
      CAPABILITIES.has(item.capability) &&
      MODALITIES.has(item.modality) &&
      OUTCOMES.has(item.outcome) &&
      ROUTES.has(item.route) &&
      TERMINATIONS.has(item.termination) &&
      notApplicable === (item.route === "not_applicable") &&
      notApplicable === (item.termination === "not_applicable") &&
      !unsafePass
    );
  });
}

function validateSubmissionMetrics(metrics, cases, suiteLength) {
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
  const scoredCount = cases.filter(
    (item) => !["not_scored", "not_applicable"].includes(item.outcome),
  ).length;
  const notApplicableCount = cases.filter((item) => item.outcome === "not_applicable").length;
  const throughput = metrics.completion_tokens_per_second;
  return (
    metrics.case_count === suiteLength &&
    metrics.semantic_pass_count === semanticCount &&
    metrics.exact_format_pass_count === formatCount &&
    metrics.scored_case_count === scoredCount &&
    scoredCount >= 1 &&
    scoredCount + notApplicableCount === suiteLength &&
    isInteger(metrics.usage_coverage_cases, 0, scoredCount) &&
    hasOneDecimalPlace(metrics.latency_ms_mean) &&
    (throughput === null ||
      (hasOneDecimalPlace(throughput) && metrics.usage_coverage_cases === scoredCount))
  );
}

async function validateSubmission(submission, registry = SUITE_REGISTRY) {
  const suite = isRecord(submission)
    ? resolveSuite(submission.profile, submission.suite_version, registry)
    : null;
  if (
    !hasExactKeys(
      submission,
      [
        "schema_version",
        "submission_id",
        "suite_version",
        "profile",
        "measurement_period",
        "validity",
        "measurement_conditions",
        "hardware",
        "runtime",
        "model",
        "settings",
        "cases",
        "metrics",
      ],
      ["runtime_configuration", "determinism"],
    ) ||
    submission.schema_version !== SUBMISSION_SCHEMA_VERSION ||
    !validateRawSubmissionNumberTypes(submission) ||
    suite === null ||
    typeof submission.submission_id !== "string" ||
    !/^[a-f0-9]{64}$/u.test(submission.submission_id) ||
    !validateHardware(submission.hardware) ||
    !validateRuntime(submission.runtime) ||
    (Object.hasOwn(submission, "runtime_configuration") &&
      !validateRuntimeConfiguration(submission.runtime_configuration)) ||
    !PUBLIC_VALIDITIES.has(submission.validity) ||
    !validateMeasurementPeriod(submission.measurement_period) ||
    !validateMeasurementConditions(submission.measurement_conditions) ||
    submission.validity !== derivedMeasurementValidity(submission.measurement_conditions) ||
    (Object.hasOwn(submission, "determinism") &&
      !validateDeterminism(submission.determinism)) ||
    !validateModel(submission.model) ||
    !validateSettings(
      submission.settings,
      submission.model.declared_context_tokens,
      submission.runtime_configuration,
    ) ||
    !validateCases(submission.cases, suite) ||
    !validateSubmissionMetrics(submission.metrics, submission.cases, suite.length) ||
    containsStaticProhibitedData(submission)
  ) {
    throw new Error("Submission data does not match the minimized public schema.");
  }
  if (submission.submission_id !== (await computeSubmissionId(submission))) {
    throw new Error("Submission content hash does not match its public payload.");
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

function entryValidity(entry) {
  return LEADERBOARD_VALIDITIES.has(entry.validity)
    ? entry.validity
    : "legacy_unreported";
}

function entryMeasurementPeriod(entry) {
  return validateMeasurementPeriod(entry.measurement_period)
    ? entry.measurement_period
    : null;
}

function filterEntriesByValidity(values, selected = "clean", period = "") {
  return values.filter((entry) => {
    const validity = entryValidity(entry);
    const matchesValidity = selected === "all" || validity === selected;
    const matchesPeriod = !period || entryMeasurementPeriod(entry) === period;
    return matchesValidity && matchesPeriod;
  });
}

function validityLabel(entry) {
  const validity = entryValidity(entry);
  return validity === "legacy_unreported"
    ? "Not reported"
    : readableEnum(validity);
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

function runtimeConfigurationText(configuration) {
  if (configuration === undefined) {
    return "Not reported";
  }
  const context =
    configuration.context_window_tokens === null
      ? "context not reported"
      : `${integer(configuration.context_window_tokens)} token context`;
  const concurrency =
    configuration.concurrent_requests === null
      ? "concurrency not reported"
      : `${integer(configuration.concurrent_requests)} concurrent request${
          configuration.concurrent_requests === 1 ? "" : "s"
        }`;
  return `${context}; ${concurrency}; speculative ${readableEnum(
    configuration.speculative_decoding,
  )}; offload ${readableEnum(configuration.offload_mode)}`;
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
  addDefinition(
    list,
    "Runtime configuration",
    runtimeConfigurationText(entry.runtime_configuration),
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
  addCell(
    row,
    validityLabel(entry),
    entryValidity(entry) === "legacy_unreported"
      ? "schema 1.0: conditions not reported"
      : "self-reported measurement conditions",
  );
  addCell(
    row,
    entryMeasurementPeriod(entry) ?? "Not reported",
    "month resolution",
  );
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
  const reasoning = Object.hasOwn(entry.settings, "reasoning_effort")
    ? ` | reasoning ${readableEnum(entry.settings.reasoning_effort)}`
    : "";
  addCell(
    row,
    `T ${settingNumber(entry.settings.temperature)} | top-p ${settingNumber(entry.settings.top_p)}`,
    `max ${integer(entry.settings.max_output_tokens)} | seed ${seed}${reasoning}`,
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
    } else if (sort === "recency") {
      const leftPeriod = entryMeasurementPeriod(left) ?? "";
      const rightPeriod = entryMeasurementPeriod(right) ?? "";
      comparison = rightPeriod.localeCompare(leftPeriod);
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

function shardId(number) {
  return String(number).padStart(6, "0");
}

function updateLoadMoreButton() {
  const hasMore =
    leaderboardIndex !== null && nextShardNumber <= leaderboardIndex.shard_count;
  elements.loadMore.hidden = !hasMore;
  elements.loadMore.disabled = loadingShard;
  elements.loadMore.textContent = loadingShard ? "Loading more results..." : "Load more results";
}

function resetLeaderboardState() {
  entries = [];
  leaderboardIndex = null;
  nextShardNumber = 1;
  loadingShard = false;
  shardRankingState = createShardRankingState();
  updateLoadMoreButton();
}

function render() {
  const query = elements.search.value.trim().toLocaleLowerCase();
  const hardware = elements.hardwareFilter.value;
  const validity = elements.validityFilter.value;
  const period = elements.periodFilter.value;
  const eligible = filterEntriesByValidity(entries, validity, period);
  const filtered = eligible.filter((entry) => {
    const haystack = `${entry.model.display_name} ${entry.model.source}`.toLocaleLowerCase();
    const matchesHardware = hardware === "all" || hardwareCategories(entry).includes(hardware);
    return matchesHardware && (!query || haystack.includes(query));
  });
  const visible = sortedEntries(filtered, elements.sort.value);
  const shown =
    visible.length === entries.length
      ? `${integer(entries.length)} loaded result${entries.length === 1 ? "" : "s"}`
      : `${integer(visible.length)} of ${integer(entries.length)} loaded results shown`;
  const total = leaderboardIndex === null ? entries.length : leaderboardIndex.entry_count;
  const hasUnloadedResults = entries.length < total;
  elements.updated.textContent =
    hasUnloadedResults
      ? `${shown} | ${integer(entries.length)} of ${integer(total)} loaded`
      : shown;

  elements.body.replaceChildren();
  updateLoadMoreButton();
  if (visible.length === 0) {
    showStatus(
      entries.length === 0
        ? "No benchmark results have been published yet."
        : validity === "clean"
          ? "No clean loaded results match these filters. Legacy and non-clean results remain available through the validity filter."
        : hasUnloadedResults
          ? "No loaded results match these filters. More published results may match; load more results to expand the searchable set."
          : "No loaded results match these filters.",
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
  )} GB | ${submission.runtime.name} ${submission.runtime.version} | Runtime configuration: ${runtimeConfigurationText(
    submission.runtime_configuration,
  )}`;
  elements.submissionPreview.hidden = false;
  elements.copySubmission.disabled = false;
  elements.downloadSubmission.disabled = false;
  elements.continueSubmission.hidden = false;
  setSubmissionStatus(
    "The closed public shape looks right. This convenience check does not replace CLI and CI privacy checks or the trusted publication boundary. A matching content hash proves integrity, not that a run occurred.",
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
    const bytes = new Uint8Array(await file.arrayBuffer());
    if (elements.submissionFile.files[0] !== file) {
      return;
    }
    if (bytes.byteLength > MAX_SUBMISSION_BYTES) {
      throw new Error("Submission data is larger than expected.");
    }
    const source = decodeStrictUtf8(bytes);
    const submission = parseStrictJson(source);
    showCheckedSubmission(await validateSubmission(submission), source);
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

async function fetchBoundedJson(url, timeoutMilliseconds = DATA_FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMilliseconds);
  try {
    const response = await fetch(url, {
      cache: "no-cache",
      credentials: "omit",
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error("Leaderboard data is unavailable.");
    }
    const contentLength = Number(response.headers.get("content-length"));
    if (Number.isFinite(contentLength) && contentLength > MAX_DATA_BYTES) {
      throw new Error("Leaderboard data is larger than expected.");
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.byteLength > MAX_DATA_BYTES) {
      throw new Error("Leaderboard data is larger than expected.");
    }
    return parseStrictJson(decodeStrictUtf8(bytes));
  } finally {
    clearTimeout(timeout);
  }
}

async function loadNextShard() {
  if (
    leaderboardIndex === null ||
    loadingShard ||
    nextShardNumber > leaderboardIndex.shard_count
  ) {
    return;
  }
  loadingShard = true;
  updateLoadMoreButton();
  try {
    const expectedId = shardId(nextShardNumber);
    const payload = validateShard(
      await fetchBoundedJson(`${SHARD_URL_PREFIX}${expectedId}${SHARD_URL_SUFFIX}`),
      expectedId,
      leaderboardIndex.schema_version,
    );
    const remainingShards = leaderboardIndex.shard_count - nextShardNumber;
    const projectedEntryCount = entries.length + payload.entry_count;
    const remainingEntries = leaderboardIndex.entry_count - projectedEntryCount;
    if (
      shardRankingState.entryCount !== entries.length ||
      projectedEntryCount > leaderboardIndex.entry_count ||
      (remainingShards === 0) !== (remainingEntries === 0) ||
      remainingEntries < remainingShards ||
      !validateAndTrackShardRanking(shardRankingState, payload.entries)
    ) {
      throw new Error("Leaderboard shards are inconsistent with their index.");
    }
    for (const entry of payload.entries) {
      entries.push(entry);
    }
    nextShardNumber += 1;
    populateHardwareFilter(entries);
    render();
  } finally {
    loadingShard = false;
    updateLoadMoreButton();
  }
}

function leaderboardUnavailable() {
  resetLeaderboardState();
  elements.updated.textContent = "Leaderboard unavailable";
  elements.loadMore.hidden = true;
  showStatus("The leaderboard could not be loaded. Try again later or view the repository for current results.");
}

async function loadLeaderboard() {
  resetLeaderboardState();
  try {
    const candidate = await fetchBoundedJson(DATA_URL);
    if (hasExactKeys(candidate, ["schema_version", "entry_count", "entries"])) {
      const payload = validatePayload(candidate);
      leaderboardIndex = null;
      entries = payload.entries;
      populateHardwareFilter(entries);
      render();
      return;
    }
    leaderboardIndex = validateIndex(candidate);
    if (leaderboardIndex.shard_count > 0) {
      await loadNextShard();
    } else {
      populateHardwareFilter(entries);
      render();
    }
  } catch (error) {
    leaderboardUnavailable();
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    SUITE_REGISTRY,
    computeSubmissionId,
    decodeStrictUtf8,
    filterEntriesByValidity,
    parseStrictJson,
    resolveSuite,
    validateSubmission,
    validateIndex,
    validateModel,
    validatePayload,
    validateShard,
    createShardRankingState,
    fetchBoundedJson,
    validateAndTrackShardRanking,
  };
}

if (typeof document !== "undefined") {
  elements.search.addEventListener("input", render);
  elements.hardwareFilter.addEventListener("change", render);
  elements.validityFilter.addEventListener("change", render);
  elements.periodFilter.addEventListener("change", render);
  elements.sort.addEventListener("change", render);
  elements.filters.addEventListener("submit", (event) => event.preventDefault());
  elements.submissionFile.addEventListener("change", checkSubmissionFile);
  elements.copySubmission.addEventListener("click", copyCheckedSubmission);
  elements.downloadSubmission.addEventListener("click", downloadCheckedSubmission);
  elements.loadMore.addEventListener("click", async () => {
    try {
      await loadNextShard();
    } catch (error) {
      leaderboardUnavailable();
    }
  });
  loadLeaderboard();
}
