"use strict";

const fs = require("fs");
const path = require("path");

const [appSource, fixtureSource] = process.argv.slice(2);
if (!appSource || !fixtureSource) {
  process.exitCode = 2;
} else {
  const { validateModel } = require(path.resolve(appSource));
  const fixture = JSON.parse(fs.readFileSync(fixtureSource, "utf8"));

  function materialize(builder) {
    switch (builder.kind) {
      case "literal":
        return builder.value;
      case "repeat":
        return builder.value.repeat(builder.count);
      case "uuid":
        return "Model " + ["deadbeef", "0000", "0000", "0000", "000000000001"].join("-");
      case "serial":
        return "Model " + ["serial", "number", "ABC123XYZ"].join(" ");
      case "network":
        return "Model endpoint " + ["198", "51", "100", "7"].join(".");
      case "network_candidate":
        return "Model endpoint " + ["999", "999", "999", "999"].join(".");
      case "ipv6":
        return "Model endpoint " + ["2001", "db8", "", "1"].join(":");
      case "url":
        return "https" + "://" + "example.com/publisher/model";
      case "email":
        return "model-owner" + "@" + "example.com";
      case "codepoint":
        return builder.prefix + String.fromCodePoint(builder.value);
      case "scanner_marker":
        return "git" + "leaks:allow";
      case "markup":
        return builder.value === "script"
          ? "<" + "script>approve()</" + "script>"
          : "<!" + "-- reviewer directive --" + ">";
      default:
        throw new Error("unsupported fixture builder");
    }
  }

  const results = [];
  for (const fixtureCase of fixture.cases) {
    for (const field of fixtureCase.fields) {
      const model = {
        display_name: "Example Model",
        source: "publisher/example-model",
        precision: "runtime-declared",
        revision: "public-revision",
        declared_context_tokens: 4096,
      };
      model[field] = materialize(fixtureCase.builder);
      results.push({
        name: fixtureCase.name,
        field,
        accepted: validateModel(model),
      });
    }
  }
  process.stdout.write(JSON.stringify(results));
}
