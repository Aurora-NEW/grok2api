import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const migrationPath = new URL("../frontend/public/creative-console-chat-defaults-v1.js", import.meta.url);
const pagePath = new URL("../frontend/src/features/creative-console/creative-console-page.tsx", import.meta.url);
const historyPrefix = "grok2api:creative-console:chat-history:";
const markerPrefix = "grok2api:creative-console:chat-defaults-v1:";

class FakeStorage {
  #entries;
  #shouldFailSetItem;

  constructor(entries = {}, { shouldFailSetItem } = {}) {
    this.#entries = new Map(Object.entries(entries));
    this.#shouldFailSetItem = shouldFailSetItem;
  }

  get length() {
    return this.#entries.size;
  }

  key(index) {
    return [...this.#entries.keys()][index] ?? null;
  }

  getItem(key) {
    return this.#entries.get(key) ?? null;
  }

  setItem(key, value) {
    if (this.#shouldFailSetItem?.(key, value)) {
      throw new Error(`setItem failed for ${key}`);
    }
    this.#entries.set(key, String(value));
  }

  removeItem(key) {
    this.#entries.delete(key);
  }
}

function runMigration(storage) {
  const source = readFileSync(migrationPath, "utf8");
  const context = vm.createContext({ localStorage: storage });
  vm.runInContext(source, context, { filename: migrationPath.pathname });
}

function testMigratesExistingSessionsAndSetsMarker() {
  const scope = "client-a";
  const historyKey = `${historyPrefix}${scope}`;
  const markerKey = `${markerPrefix}${scope}`;
  const storage = new FakeStorage({
    [historyKey]: JSON.stringify([
      { id: "first", reasoningEffort: "auto", webSearch: false, xSearch: false },
      { id: "second", reasoningEffort: "low", webSearch: false, xSearch: false },
      "preserve-non-object",
    ]),
  });

  runMigration(storage);

  assert.deepEqual(JSON.parse(storage.getItem(historyKey)), [
    { id: "first", reasoningEffort: "xhigh", webSearch: true, xSearch: true },
    { id: "second", reasoningEffort: "xhigh", webSearch: true, xSearch: true },
    "preserve-non-object",
  ]);
  assert.equal(storage.getItem(markerKey), "1");
}

function testLeavesMalformedHistoryUnchangedAndUnmarked() {
  const scope = "broken";
  const historyKey = `${historyPrefix}${scope}`;
  const markerKey = `${markerPrefix}${scope}`;
  const malformed = "{not valid JSON";
  const storage = new FakeStorage({ [historyKey]: malformed });

  runMigration(storage);

  assert.equal(storage.getItem(historyKey), malformed);
  assert.equal(storage.getItem(markerKey), null);
}

function testLeavesNonArrayHistoryUnchangedAndUnmarked() {
  const scope = "not-an-array";
  const historyKey = `${historyPrefix}${scope}`;
  const markerKey = `${markerPrefix}${scope}`;
  const nonArrayHistory = JSON.stringify({ id: "not-a-session-list" });
  const storage = new FakeStorage({ [historyKey]: nonArrayHistory });

  runMigration(storage);

  assert.equal(storage.getItem(historyKey), nonArrayHistory);
  assert.equal(storage.getItem(markerKey), null);
}

function testRestoresOriginalHistoryWhenMarkerWriteFails() {
  const scope = "marker-write-failure";
  const historyKey = `${historyPrefix}${scope}`;
  const markerKey = `${markerPrefix}${scope}`;
  const originalHistory = '[{ "id": "manual", "reasoningEffort": "auto", "webSearch": false, "xSearch": false }]';
  const storage = new FakeStorage(
    { [historyKey]: originalHistory },
    { shouldFailSetItem: (key) => key === markerKey },
  );

  runMigration(storage);

  assert.equal(storage.getItem(historyKey), originalHistory);
  assert.equal(storage.getItem(markerKey), null);
}

function testMarkerPreservesManualChoicesOnLaterExecution() {
  const scope = "client-b";
  const historyKey = `${historyPrefix}${scope}`;
  const storage = new FakeStorage({
    [historyKey]: JSON.stringify([{ id: "manual", reasoningEffort: "auto", webSearch: false, xSearch: false }]),
  });

  runMigration(storage);
  storage.setItem(historyKey, JSON.stringify([{ id: "manual", reasoningEffort: "auto", webSearch: false, xSearch: false }]));
  runMigration(storage);

  assert.deepEqual(JSON.parse(storage.getItem(historyKey)), [
    { id: "manual", reasoningEffort: "auto", webSearch: false, xSearch: false },
  ]);
}

function testUnavailableLocalStorageDoesNotThrow() {
  const source = readFileSync(migrationPath, "utf8");
  const context = vm.createContext({});
  Object.defineProperty(context, "localStorage", {
    get() {
      throw new Error("storage unavailable");
    },
  });

  assert.doesNotThrow(() => vm.runInContext(source, context, { filename: migrationPath.pathname }));
}

function runMigrationTests() {
  testMigratesExistingSessionsAndSetsMarker();
  testLeavesMalformedHistoryUnchangedAndUnmarked();
  testLeavesNonArrayHistoryUnchangedAndUnmarked();
  testRestoresOriginalHistoryWhenMarkerWriteFails();
  testMarkerPreservesManualChoicesOnLaterExecution();
  testUnavailableLocalStorageDoesNotThrow();
}

function assertFuturePageDefaults(source = readFileSync(pagePath, "utf8")) {
  const blankSessionStart = source.indexOf("function createBlankChatSession(model: string): ChatSession {");
  const sessionTitleStart = source.indexOf("function createChatSessionTitle", blankSessionStart);
  assert.ok(blankSessionStart >= 0, "createBlankChatSession function is missing");
  assert.ok(sessionTitleStart > blankSessionStart, "createChatSessionTitle must follow createBlankChatSession");

  const blankSessionSource = source.slice(blankSessionStart, sessionTitleStart);
  assert.match(blankSessionSource, /reasoningEffort:\s*"xhigh"/);
  assert.match(blankSessionSource, /webSearch:\s*true/);
  assert.match(blankSessionSource, /xSearch:\s*true/);

  const clearConversationStart = source.indexOf("function clearConversation(): void {");
  const startNewConversationStart = source.indexOf("function startNewConversation(): void {");
  assert.ok(clearConversationStart >= 0, "clearConversation function is missing");
  assert.ok(startNewConversationStart > clearConversationStart, "startNewConversation must follow clearConversation");

  const clearConversationSource = source.slice(clearConversationStart, startNewConversationStart);
  assert.match(clearConversationSource, /setReasoningEffort\(blank\.reasoningEffort\)/);
  assert.match(clearConversationSource, /setWebSearch\(blank\.webSearch\)/);
  assert.match(clearConversationSource, /setXSearch\(blank\.xSearch\)/);
}

function testFutureDefaultsRequireClearConversationSetters() {
  const source = [
    'const blank = { reasoningEffort: "xhigh", webSearch: true, xSearch: true };',
    "function clearConversation(): void {",
    "  resetComposer();",
    "}",
    "function startNewConversation(): void {",
    "  setReasoningEffort(blank.reasoningEffort);",
    "  setWebSearch(blank.webSearch);",
    "  setXSearch(blank.xSearch);",
    "}",
  ].join("\n");

  assert.throws(() => assertFuturePageDefaults(source));
}

function assertStoredSessionDefaultsAreForced(source = readFileSync(pagePath, "utf8")) {
  const parserStart = source.indexOf("function parseChatSession(value: unknown): ChatSession[] {");
  const messageParserStart = source.indexOf("function parseConversationMessage", parserStart);
  assert.ok(parserStart >= 0, "parseChatSession function is missing");
  assert.ok(messageParserStart > parserStart, "parseConversationMessage must follow parseChatSession");

  const parserSource = source.slice(parserStart, messageParserStart);
  assert.match(parserSource, /reasoningEffort:\s*"xhigh"/);
  assert.match(parserSource, /webSearch:\s*true/);
  assert.match(parserSource, /xSearch:\s*true/);
  assert.doesNotMatch(parserSource, /value\.(reasoningEffort|webSearch|xSearch)/);

  const switchStart = source.indexOf("function switchConversation(targetId: string): void {");
  const promptHandlerStart = source.indexOf("function handlePromptKeyDown", switchStart);
  assert.ok(switchStart >= 0, "switchConversation function is missing");
  assert.ok(promptHandlerStart > switchStart, "handlePromptKeyDown must follow switchConversation");

  const switchSource = source.slice(switchStart, promptHandlerStart);
  assert.match(switchSource, /setReasoningEffort\("xhigh"\);/);
  assert.match(switchSource, /setWebSearch\(true\);/);
  assert.match(switchSource, /setXSearch\(true\);/);
  assert.doesNotMatch(switchSource, /setReasoningEffort\(target\.reasoningEffort\)/);
  assert.doesNotMatch(switchSource, /setWebSearch\(target\.webSearch\)/);
  assert.doesNotMatch(switchSource, /setXSearch\(target\.xSearch\)/);
}

runMigrationTests();

if (process.argv.includes("--migration-only")) {
  console.log("creative console chat defaults migration tests passed");
} else {
  testFutureDefaultsRequireClearConversationSetters();
  assertFuturePageDefaults();
  assertStoredSessionDefaultsAreForced();
  console.log("creative console chat defaults tests passed");
}
