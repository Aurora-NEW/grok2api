export type CreativeChatDefaults = {
  reasoningEffort: "xhigh";
  webSearch: true;
  xSearch: true;
};

export function createCreativeChatDefaults(): CreativeChatDefaults {
  return {
    reasoningEffort: "xhigh",
    webSearch: true,
    xSearch: true,
  };
}

export function withCreativeChatDefaults<T extends object>(value: T): T & CreativeChatDefaults {
  return { ...value, ...createCreativeChatDefaults() };
}
