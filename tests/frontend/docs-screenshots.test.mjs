import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { screenshotFixture } from "../../scripts/docs-screenshots/fixture.js";

test("synthetic screenshot messages retain node identity consistency", () => {
  const nodes = new Map(
    screenshotFixture.sources.flatMap((source) =>
      (source.nodes || []).map((node) => [`${node.protocol}:${node.id}`, node.name]),
    ),
  );

  for (const message of screenshotFixture.messages) {
    const expected = nodes.get(`${message.protocol}:${message.from_id}`);
    if (expected) assert.equal(message.from_name, expected);
  }
});

test("synthetic screenshot sources belong to their declared server", () => {
  for (const server of screenshotFixture.servers) {
    const sources = screenshotFixture.sources.filter(
      (source) => source.entry_id === server.entry_id,
    );
    assert.equal(sources.length, server.source_count);
  }
  assert.equal(
    screenshotFixture.sources.length,
    screenshotFixture.servers.reduce((total, server) => total + server.source_count, 0),
  );
});

test("screenshot harness is fail-closed and network isolated", async () => {
  const generator = await readFile(
    new URL("../../scripts/generate-doc-screenshots.mjs", import.meta.url),
    "utf8",
  );
  const harness = await readFile(
    new URL("../../scripts/docs-screenshots/harness.js", import.meta.url),
    "utf8",
  );

  assert.match(generator, /default-src 'none'/);
  assert.match(generator, /connect-src 'none'/);
  assert.match(generator, /form-action 'none'/);
  assert.match(generator, /host-resolver-rules=MAP \* ~NOTFOUND/);
  assert.match(generator, /exactRoutes/);
  assert.match(generator, /containedRealpath/);
  assert.match(generator, /Private route was served/);
  assert.match(generator, /--dump-dom.*--screenshot=/s);
  assert.match(generator, /data-screenshot-error=/);
  assert.match(generator, /mkdtemp/);
  assert.match(harness, /Unhandled synthetic WebSocket request/);
  assert.match(harness, /meshmonitor\/notification_settings/);
  assert.match(harness, /_mapStyle = "tiles-off"/);
});
