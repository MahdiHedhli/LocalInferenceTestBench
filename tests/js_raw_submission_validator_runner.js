"use strict";

const fs = require("fs");

const [appSource, ...submissionSources] = process.argv.slice(2);
if (!appSource || submissionSources.length === 0) {
  process.exit(2);
}

const { decodeStrictUtf8, parseStrictJson, validateSubmission } = require(appSource);

async function main() {
  const results = [];
  for (const sourcePath of submissionSources) {
    try {
      const source = decodeStrictUtf8(fs.readFileSync(sourcePath));
      await validateSubmission(parseStrictJson(source));
      results.push(true);
    } catch (error) {
      results.push(false);
    }
  }
  process.stdout.write(JSON.stringify(results));
}

main().catch(() => process.exit(1));
