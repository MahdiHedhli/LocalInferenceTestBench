"use strict";

const fs = require("fs");

const [appSource, submissionSource, fixtureSource] = process.argv.slice(2);
if (!appSource || !submissionSource || !fixtureSource) {
  process.exit(2);
}

const { computeSubmissionId, validateSubmission } = require(appSource);
const base = JSON.parse(fs.readFileSync(submissionSource, "utf8"));
const fixtures = JSON.parse(fs.readFileSync(fixtureSource, "utf8"));

function applyOperation(target, operation) {
  const path = operation.path;
  let parent = target;
  for (const part of path.slice(0, -1)) {
    parent = parent[part];
  }
  const key = path[path.length - 1];
  if (operation.op === "delete") {
    delete parent[key];
    return;
  }
  if (operation.op === "set") {
    parent[key] = JSON.parse(JSON.stringify(operation.value));
    return;
  }
  throw new Error("unsupported fixture operation");
}

async function main() {
  const results = {};
  for (const fixture of fixtures.cases) {
    const candidate = JSON.parse(JSON.stringify(base));
    for (const operation of fixture.operations) {
      applyOperation(candidate, operation);
    }
    candidate.submission_id = await computeSubmissionId(candidate);
    try {
      await validateSubmission(candidate);
      results[fixture.name] = true;
    } catch (error) {
      results[fixture.name] = false;
    }
  }
  process.stdout.write(JSON.stringify(results));
}

main().catch(() => process.exit(1));
