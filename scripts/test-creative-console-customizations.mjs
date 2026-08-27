import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const pageURL = new URL("../frontend/src/features/creative-console/creative-console-page.tsx", import.meta.url);
const source = readFileSync(pageURL, "utf8");

function section(startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start + startMarker.length);
  assert.ok(start >= 0, `${startMarker} is missing`);
  assert.ok(end > start, `${endMarker} must follow ${startMarker}`);
  return source.slice(start, end);
}

assert.doesNotMatch(source, /DEEIX Chat|DEEIX-AI\/DEEIX-Chat/);
assert.match(source, /from "@\/features\/creative-console\/creative-console-defaults"/);
assert.match(source, /grok2api:creative-console:chat-history:/);
assert.match(source, /grok-4\.20-0309-reasoning/);

const clearConversation = section("function clearConversation(): void {", "function startNewConversation(): void {");
assert.match(clearConversation, /setReasoningEffort\(blank\.reasoningEffort\)/);
assert.match(clearConversation, /setWebSearch\(blank\.webSearch\)/);
assert.match(clearConversation, /setXSearch\(blank\.xSearch\)/);

const newConversation = section("function startNewConversation(): void {", "function switchConversation(targetId: string): void {");
assert.match(newConversation, /setReasoningEffort\(blank\.reasoningEffort\)/);
assert.match(newConversation, /setWebSearch\(blank\.webSearch\)/);
assert.match(newConversation, /setXSearch\(blank\.xSearch\)/);

const switchConversation = section("function switchConversation(targetId: string): void {", "function handlePromptKeyDown");
assert.match(switchConversation, /const defaults = createCreativeChatDefaults\(\)/);
assert.match(switchConversation, /setReasoningEffort\(defaults\.reasoningEffort\)/);
assert.match(switchConversation, /setWebSearch\(defaults\.webSearch\)/);
assert.match(switchConversation, /setXSearch\(defaults\.xSearch\)/);
assert.doesNotMatch(switchConversation, /set(?:ReasoningEffort|WebSearch|XSearch)\(target\./);

const blankSession = section("function createBlankChatSession(model: string): ChatSession {", "function createChatSessionTitle");
assert.match(blankSession, /withCreativeChatDefaults\(\{/);

const parser = section("function parseChatSession(value: unknown): ChatSession[] {", "function parseConversationMessage");
assert.match(parser, /withCreativeChatDefaults\(\{/);
assert.match(parser, /messages/);
assert.match(parser, /promptCacheKey/);
assert.match(parser, /model:/);

console.log("Creative Console customization source tests passed");
