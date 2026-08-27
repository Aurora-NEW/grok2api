export type CreativeChatDefaults = {
  reasoningEffort: "xhigh";
  webSearch: true;
  xSearch: true;
};

const preferredCreativeChatModel = "grok-4.20-multi-agent-0309";

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

export function selectDefaultCreativeChatModel(models: ReadonlyArray<{ publicId: string }>): string {
  return models.find((model) => model.publicId === preferredCreativeChatModel)?.publicId ?? models[0]?.publicId ?? "";
}
