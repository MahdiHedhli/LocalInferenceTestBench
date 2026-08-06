"use strict";

const fs = require("fs");

const [appSource, payloadSource] = process.argv.slice(2);
if (!appSource || !payloadSource) {
  process.exit(2);
}

const { validatePayload } = require(appSource);
const payload = JSON.parse(fs.readFileSync(payloadSource, "utf8"));

(async () => {
  try {
    await validatePayload(payload);
    process.stdout.write("accepted\n");
  } catch (error) {
    process.stdout.write("rejected\n");
  }
})();
