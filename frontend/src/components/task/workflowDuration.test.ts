import { workflowDurationDescription } from "./workflowDuration";

it("makes the default-workflow duration limitation explicit", () => {
  expect(workflowDurationDescription(undefined, 6)).toContain("工作流默认值");
});

it("previews exactly the aligned frame count used by the provider", () => {
  const profile = { id: "p", name: "预设", resolution: "", quality: "", workflowFile: "w.json", enabled: true, numericBindings: [{ portId: "7:frames:2", source: "frameCount" as const, fps: 24, frameMultiple: 4, frameOffset: 1 }] };
  expect(workflowDurationDescription(profile, 6)).toBe("传入工作流：145 帧（24 fps）");
  expect(workflowDurationDescription(profile, 7)).toBe("传入工作流：169 帧（24 fps）");
});
