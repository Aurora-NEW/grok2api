import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  createCreativeChatDefaults,
  selectDefaultCreativeChatModel,
  withCreativeChatDefaults,
} from "./creative-console-defaults.ts";

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

  it("prefers the Multi-Agent model for a fresh conversation", () => {
    const models = [
      { publicId: "grok-build-0.1" },
      { publicId: "grok-4.20-multi-agent-0309" },
      { publicId: "grok-4.5" },
    ];

    assert.equal(selectDefaultCreativeChatModel(models), "grok-4.20-multi-agent-0309");
    assert.equal(selectDefaultCreativeChatModel([{ publicId: "grok-4.5" }]), "grok-4.5");
    assert.equal(selectDefaultCreativeChatModel([]), "");
  });
});
