const canonicalEntry = "/assets/index-DVIk9Mqh.js";
const cacheMarker = "grok2api:frontend-entry:v3-20260814";

let refreshed = false;
try {
  refreshed = window.localStorage.getItem(cacheMarker) === "1";
} catch {
  // Continue without persistent cache state when browser storage is unavailable.
}

if (!refreshed) {
  const response = await fetch(canonicalEntry, { cache: "reload" });
  if (!response.ok) throw new Error(`Failed to refresh frontend entry: HTTP ${response.status}`);
  await response.arrayBuffer();
  try {
    window.localStorage.setItem(cacheMarker, "1");
  } catch {
    // A repeat refresh on the next page load is safe.
  }
}

await import(canonicalEntry);
