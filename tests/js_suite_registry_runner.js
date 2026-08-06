"use strict";

const fs = require("fs");

const [appSource, submissionSource, registrySource] = process.argv.slice(2);
if (!appSource || !submissionSource || !registrySource) {
  process.exit(2);
}

const { validateSubmission } = require(appSource);
const submission = JSON.parse(fs.readFileSync(submissionSource, "utf8"));
const registry = JSON.parse(fs.readFileSync(registrySource, "utf8"));

async function main() {
  try {
    await validateSubmission(submission, registry);
    process.stdout.write("accepted\n");
  } catch (error) {
    process.stdout.write("rejected\n");
  }
}

main().catch(() => process.exit(1));
