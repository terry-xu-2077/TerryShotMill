import type { ProjectAsset } from "../../domain/storyboard";

export const categoryLabel: Record<ProjectAsset["category"], string> = {
  character: "角色",
  scene: "场景",
  prop: "道具",
  reference: "参考",
};
