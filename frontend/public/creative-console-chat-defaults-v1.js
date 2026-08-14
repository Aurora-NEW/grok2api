(() => {
  const historyPrefix = "grok2api:creative-console:chat-history:";
  const markerPrefix = "grok2api:creative-console:chat-defaults-v1:";

  try {
    const storage = localStorage;
    const historyKeys = [];

    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (typeof key === "string" && key.startsWith(historyPrefix)) {
        historyKeys.push(key);
      }
    }

    for (const historyKey of historyKeys) {
      try {
        const markerKey = `${markerPrefix}${historyKey.slice(historyPrefix.length)}`;
        if (storage.getItem(markerKey) === "1") continue;

        const savedHistory = storage.getItem(historyKey);
        if (savedHistory === null) continue;

        const sessions = JSON.parse(savedHistory);
        if (!Array.isArray(sessions)) continue;

        const migratedSessions = sessions.map((session) => (
          session !== null && typeof session === "object" && !Array.isArray(session)
            ? { ...session, reasoningEffort: "xhigh", webSearch: true, xSearch: true }
            : session
        ));

        storage.setItem(historyKey, JSON.stringify(migratedSessions));
        try {
          storage.setItem(markerKey, "1");
        } catch {
          try {
            storage.removeItem(markerKey);
          } catch {
            // Ignore marker cleanup failures so the history rollback can still run.
          }
          try {
            storage.setItem(historyKey, savedHistory);
          } catch {
            // Ignore rollback failures so application startup can continue.
          }
        }
      } catch {
        // Ignore corrupt or unavailable entries so application startup can continue.
      }
    }
  } catch {
    // Private browsing and storage policies can make localStorage unavailable.
  }
})();
