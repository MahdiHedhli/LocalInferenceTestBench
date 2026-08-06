"use strict";

const fs = require("fs");
const path = require("path");

const [appSource, leaderboardSource] = process.argv.slice(2);
if (!appSource || !leaderboardSource) {
  process.exitCode = 2;
} else {
  const {
    validateIndex,
    validatePayload,
    validateShard,
  } = require(path.resolve(appSource));
  const legacy = JSON.parse(fs.readFileSync(leaderboardSource, "utf8"));
  const index = {
    index_version: "1.0",
    schema_version: legacy.schema_version,
    entry_count: legacy.entry_count,
    shard_count: legacy.entry_count === 0 ? 0 : 1,
  };
  const shard = {
    index_version: "1.0",
    schema_version: legacy.schema_version,
    shard_id: "000001",
    entry_count: legacy.entry_count,
    entries: legacy.entries,
  };

  async function accepts(callback) {
    try {
      await callback();
      return true;
    } catch (error) {
      return false;
    }
  }

  (async () => {
    const results = {
      legacy: await accepts(() => validatePayload(legacy)),
      index: await accepts(() => validateIndex(index)),
      index_extra_key: await accepts(() =>
        validateIndex({ ...index, path: "not-accepted" }),
      ),
      index_nonzero_entries_zero_shards: await accepts(() =>
        validateIndex({ ...index, entry_count: 1, shard_count: 0 }),
      ),
      index_more_shards_than_entries: await accepts(() =>
        validateIndex({ ...index, entry_count: 1, shard_count: 2 }),
      ),
      shard: await accepts(() => validateShard(shard, "000001", legacy.schema_version)),
      shard_extra_key: await accepts(() =>
        validateShard({ ...shard, path: "not-accepted" }, "000001", legacy.schema_version),
      ),
      shard_wrong_id: await accepts(() =>
        validateShard(shard, "000002", legacy.schema_version),
      ),
      legacy_reordered_tie:
        legacy.entries.length < 2
          ? "skipped"
          : await accepts(() =>
              validatePayload({
                ...legacy,
                entries: [legacy.entries[1], legacy.entries[0], ...legacy.entries.slice(2)],
              }),
            ),
    };
    process.stdout.write(JSON.stringify(results));
  })();
}
