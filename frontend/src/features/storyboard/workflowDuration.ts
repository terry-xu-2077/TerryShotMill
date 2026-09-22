import type { ComfyUIWorkflowProfile } from "../../gateways/projectGateway";

export function workflowDurationDescription(profile: ComfyUIWorkflowProfile | undefined, seconds: number): string {
  const bindings = profile?.numericBindings?.filter((binding) => binding.source !== "constant") ?? [];
  if (!bindings.length) return "分辨率与秒数传入 Bridge 选择器；未接入时使用工作流默认值。";
  return bindings.map((binding) => {
    if (binding.source === "durationSeconds") return `传入工作流：${seconds} 秒`;
    const fps = binding.fps ?? 24, multiple = binding.frameMultiple ?? 1, offset = binding.frameOffset ?? 0;
    const frames = Math.ceil((seconds * fps - offset) / multiple) * multiple + offset;
    return `传入工作流：${frames} 帧（${fps} fps）`;
  }).join("；");
}
