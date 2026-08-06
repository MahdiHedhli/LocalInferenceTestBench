# Data model: Guided benchmark failure reporting

## Failure signal

An internal value with exactly:

- `phase`: `preflight`, `case_execution`, or `runner_internal`;
- `failure_category`: one of the nine eligible categories.

It contains no exception, message, case ID, model ID, count, endpoint, path, or time. A completed
report selects one category with this priority:

`response_too_large` → `invalid_json` → `protocol_error` → `server_error` →
`request_rejected` → `timeout` → `network_error` → `http_error`.

## Failure issue draft schema `1.0`

| Field | Type | Rule |
|-------|------|------|
| `schema_version` | string | fixed `1.0` |
| `report_type` | string | fixed `benchmark_execution_failure` |
| `litb_version` | string | code-controlled semantic version |
| `command` | string | fixed `run` |
| `profile` | enum | `smoke` or `standard` |
| `suite_version` | string | registered suite version; currently `1.0` |
| `phase` | enum | `preflight`, `case_execution`, `runner_internal` |
| `failure_category` | enum | exact FR-002 allowlist |
| `os_family` | enum | `macos`, `linux`, `windows`, `other` |
| `python_series` | enum | `python_3_11` through `python_3_14`, or `other` |
| `architecture` | enum | `arm64`, `x86_64`, `other` |
| `hardware_class` | enum | `cpu_only`, `shared_accelerator`, `discrete_accelerator`, `mixed_accelerator`, `unknown` |
| `runtime` | object | exact `name`, `version`, `backend`; descriptor-grade public text or `unknown` |

Unknown platform strings collapse to enum `other`; they are never copied. An absent or invalid
descriptor produces `hardware_class: unknown` and three runtime `unknown` values.
A valid descriptor may itself use `unknown` for an individual runtime field it cannot verify; the
draft preserves that already-reviewed public value without inferring a replacement.

## Issue composer

- Base URL: fixed repository `/issues/new` HTTPS path.
- Title: fixed prefix plus only the phase and category enums; bounded to 120 ASCII characters.
- Body: fixed explanatory prose plus canonical, ASCII JSON for the exact draft; at most 4096 UTF-8
  bytes.
- Query: exactly `title` and `body`, constructed with `urllib.parse.urlencode`.
- Complete encoded URL: at most 8192 bytes; excess fails without truncation.

The browser handoff transmits the query to GitHub. It does not create an issue; GitHub Submit is the
public mutation. The implementation stores no draft file and receives no creation result.

## State transition

    eligible failure
        -> local closed draft
        -> complete preview and disclosure
        -> declined (no browser/network)
        -> normalized single-letter ASCII y -> browser handoff -> GitHub composer -> optional Submit

Every branch returns the benchmark's original status.
