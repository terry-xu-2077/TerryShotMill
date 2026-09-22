import type { GenerationTask, StoryboardDomainSnapshot } from "../domain/storyboard";
import { mockStoryboard } from "./storyboard";

export type DirectorProject = {
  taskGenerationNotes?: Record<string, string | null>;
  taskWarnings?: Record<string, string[]>;
  taskNewResults?: Record<string, { video?: string | null; prompt?: string | null }>;
  automaticCoverUrl?: string;
  runtime?: import("../gateways/projectGateway").ProjectWorkspaceView["runtime"];
  taskTimings?: Record<string, import("../gateways/projectGateway").TaskTiming>;
  id: string;
  title: string;
  description: string;
  useDescriptionForAiPrompt: boolean;
  coverUrl?: string;
  coverAssetId?: string | null;
  snapshot: StoryboardDomainSnapshot;
};

function cloneStoryboard() {
  return structuredClone(mockStoryboard) as StoryboardDomainSnapshot;
}

function keepFirstTasks(snapshot: StoryboardDomainSnapshot, count: number): StoryboardDomainSnapshot {
  const taskIds = new Set(snapshot.tasks.slice(0, count).map((task) => task.id));
  const jobIds = new Set(snapshot.jobs.filter((job) => taskIds.has(job.taskId)).map((job) => job.id));
  return {
    ...snapshot,
    tasks: snapshot.tasks.filter((task) => taskIds.has(task.id)),
    taskPlacements: snapshot.taskPlacements.filter((placement) => taskIds.has(placement.taskId)),
    generationContextLinks: snapshot.generationContextLinks.filter(
      (link) => taskIds.has(link.sourceTaskId) && taskIds.has(link.targetTaskId),
    ),
    jobs: snapshot.jobs.filter((job) => taskIds.has(job.taskId)),
    results: snapshot.results.filter((result) => jobIds.has(result.jobId)),
  };
}

function firstProjectSnapshot() {
  const snapshot = keepFirstTasks(cloneStoryboard(), 3);
  const titles = ["特瑞在荒漠驰骋", "越过断层台地", "驶入临时基地"];
  const prompts = [
    "特瑞驾驶越野车穿过荒漠，低机位贴近车轮和飞散砂石，远处可见基地轮廓。",
    "越野车冲上断层边缘后短暂腾空，落地时悬挂压缩，保持上一镜运动方向。",
    "车辆进入临时基地，矿工与搭建中的设施逐渐进入画面，节奏由快转稳。",
  ];
  snapshot.tasks = snapshot.tasks.map((task, index): GenerationTask => ({
    ...task,
    title: titles[index] ?? task.title,
    summary: prompts[index] ?? task.summary,
    finalPrompt: prompts[index] ?? task.finalPrompt,
    state: index === 0 ? "completed" : index === 1 ? "running" : "draft",
    progress: index === 1 ? 43 : undefined,
    primaryResultId: index === 0 ? "result-arrival-2" : task.primaryResultId,
  }));
  return snapshot;
}

function secondProjectSnapshot() {
  const snapshot = keepFirstTasks(cloneStoryboard(), 4);
  snapshot.tasks = snapshot.tasks.map((task, index): GenerationTask => ({
    ...task,
    title: ["山门夜雨", "诡巷追踪", "纸人开眼", "古井回声"][index] ?? task.title,
    summary: "等待导演确认提示词与素材。",
    finalPrompt: "",
    aiPrompt: "",
    state: "draft",
    progress: undefined,
    jobIds: [],
    primaryResultId: undefined,
  }));
  snapshot.jobs = [];
  snapshot.results = [];
  return snapshot;
}

function thirdProjectSnapshot() {
  const snapshot = keepFirstTasks(cloneStoryboard(), 4);
  snapshot.tasks = snapshot.tasks.map((task, index): GenerationTask => ({
    ...task,
    title: ["重返教室", "月考逆袭", "操场冲突", "成绩公布"][index] ?? task.title,
    summary: "已完成主要生成版本。",
    state: "completed",
    progress: undefined,
  }));
  return snapshot;
}

export function makeMockProjects(): DirectorProject[] {
  return [
    {
      id: "project-offworld",
      title: "异星边境 初到基地",
      description: "异星殖民地开荒题材。重点保持荒漠、基地建设、矿工群像与现实电影感，镜头之间要有明确的空间和运动连续性。",
      useDescriptionForAiPrompt: true,
      coverUrl: "assets/storyboard/warehouse.webp",
      snapshot: firstProjectSnapshot(),
    },
    {
      id: "project-immortal",
      title: "诡道异仙 第一部",
      description: "东方志怪与诡异修仙题材，避免现代感道具与过度游戏化视觉。",
      useDescriptionForAiPrompt: true,
      snapshot: secondProjectSnapshot(),
    },
    {
      id: "project-school",
      title: "重生之我是高中学霸",
      description: "现代校园短剧，画面自然写实，人物关系和校园空间保持连续。",
      useDescriptionForAiPrompt: false,
      coverUrl: "assets/storyboard/rain.webp",
      snapshot: thirdProjectSnapshot(),
    },
  ];
}

export function makeEmptyProject(title: string, id = `project-${Date.now()}`): DirectorProject {
  const snapshot = cloneStoryboard();
  snapshot.tasks = [];
  snapshot.taskPlacements = [];
  snapshot.generationContextLinks = [];
  snapshot.jobs = [];
  snapshot.results = [];
  snapshot.assets = [];
  return {
    id,
    title,
    description: "",
    useDescriptionForAiPrompt: false,
    snapshot,
  };
}
