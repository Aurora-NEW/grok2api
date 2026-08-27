import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { createCreativeChatDefaults, withCreativeChatDefaults } from "./creative-console-defaults.ts";

describe("Creative Console chat defaults", () => {
  it("returns Web and X search enabled with xhigh reasoning", () => {
    assert.deepEqual(createCreativeChatDefaults(), {
      reasoningEffort: "xhigh",
      webSearch: true,
      xSearch: true,
    });
  });

  it("overrides only controls while preserving stored conversation data", () => {
    const messages = [{ id: "message-1", role: "user", content: "keep me" }];
    const stored = {
      id: "session-1",
      model: "grok-chat-fast",
      promptCacheKey: "cache-1",
      messages,
      reasoningEffort: "auto",
      webSearch: false,
      xSearch: false,
    };

    const normalized = withCreativeChatDefaults(stored);

    assert.equal(normalized.id, stored.id);
    assert.equal(normalized.model, stored.model);
    assert.equal(normalized.promptCacheKey, stored.promptCacheKey);
    assert.equal(normalized.messages, messages);
    assert.equal(normalized.reasoningEffort, "xhigh");
    assert.equal(normalized.webSearch, true);
    assert.equal(normalized.xSearch, true);
    assert.equal(stored.reasoningEffort, "auto");
  });
});
