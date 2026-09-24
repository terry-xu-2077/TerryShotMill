import { describe, expect, it } from "vitest";

import { listTasksInStoryOrder } from "../../domain/storyboard";
import { mockStoryboard } from "../../mock/storyboard";
import {
  addAssetBindingToTasks,
  applyProfileToTasks,
  cloneTaskAsDraft,
  deleteTasksWithoutHistory,
  insertTaskAfter,
  moveTasksInStoryOrder,
  replaceTaskAssetBindings,
  updateSceneMetadata,
  updateTaskIntent,
} from "./storyboardMutations";
import { queueReadyTasks } from "./storyboardExecution";
import { mockGenerationProfiles } from "../../mock/generationProfiles";

describe("storyboard Task mutations", () => {
  it("duplicates Task content without copying execution history or Context", () => {
    const source = mockStoryboard.tasks.find((task) => task.id === "task-harbor-arrival")!;
    const copy = cloneTaskAsDraft(source, "task-copy", "T01-004");

    expect(copy.visualBeats).toHaveLength(3);
    expect(copy.visualBeats.map((beat) => beat.id)).not.toEqual(source.visualBeats.map((beat) => beat.id));
    expect(copy.state).toBe("draft");
    expect(copy.jobIds).toEqual([]);
    expect(copy.primaryResultId).toBeUndefined();
    expect(copy.contextLinkIds).toEqual([]);
  });

  it("inserts a new Task after the selected Task and keeps stable identities", () => {
    const source = mockStoryboard.tasks.find((task) => task.id === "task-hall-projector")!;
    const copy = cloneTaskAsDraft(source, "task-inserted", "T01-004");
    const updated = insertTaskAfter(mockStoryboard, copy, "scene-harbor", "task-hall-projector");

    expect(listTasksInStoryOrder(updated, "scene-harbor").map((task) => task.id)).toEqual([
      "task-harbor-arrival",
      "task-hall-projector",
      "task-inserted",
      "task-wall-image",
    ]);
    expect(updated.tasks.find((task) => task.id === "task-hall-projector")).toBe(source);
  });

  it("deletes only Tasks without immutable history", () => {
    const result = deleteTasksWithoutHistory(mockStoryboard, ["task-harbor-arrival", "task-draft"]);

    expect(result.protectedIds).toEqual(["task-harbor-arrival"]);
    expect(result.deletedIds).toEqual(["task-draft"]);
    expect(result.snapshot.tasks.some((task) => task.id === "task-harbor-arrival")).toBe(true);
    expect(result.snapshot.tasks.some((task) => task.id === "task-draft")).toBe(false);
    expect(result.snapshot.jobs).toEqual(mockStoryboard.jobs);
    expect(result.snapshot.results).toEqual(mockStoryboard.results);
  });

  it("moves Tasks across Scenes by changing placement without rewriting identity or history", () => {
    const result = moveTasksInStoryOrder(
      mockStoryboard,
      ["task-harbor-arrival"],
      "scene-hall",
      "task-voice",
    );

    expect(result.changed).toBe(true);
    expect(listTasksInStoryOrder(result.snapshot, "scene-harbor").map((task) => task.id)).toEqual([
      "task-hall-projector",
      "task-wall-image",
    ]);
    expect(listTasksInStoryOrder(result.snapshot, "scene-hall").map((task) => task.id)).toEqual([
      "task-harbor-arrival",
      "task-voice",
      "task-corridor",
      "task-draft",
    ]);
    expect(result.snapshot.tasks).toBe(mockStoryboard.tasks);
    expect(result.snapshot.jobs).toBe(mockStoryboard.jobs);
    expect(result.snapshot.results).toBe(mockStoryboard.results);
    expect(result.snapshot.generationContextLinks.find((link) => link.id === "context-arrival-projector")?.stale).toBe(true);
  });

  it("keeps the relative order of a multi-selection while moving it", () => {
    const result = moveTasksInStoryOrder(
      mockStoryboard,
      ["task-wall-image", "task-harbor-arrival"],
      "scene-hall",
    );

    expect(listTasksInStoryOrder(result.snapshot, "scene-hall").map((task) => task.id)).toEqual([
      "task-voice",
      "task-corridor",
      "task-draft",
      "task-harbor-arrival",
      "task-wall-image",
    ]);
  });

  it("edits current intent and Scene metadata without touching immutable execution history", () => {
    const withTaskEdit = updateTaskIntent(mockStoryboard, "task-harbor-arrival", { title: "新的任务意图" });
    const withSceneEdit = updateSceneMetadata(withTaskEdit, "scene-harbor", { location: "新地点" });

    expect(withSceneEdit.tasks.find((task) => task.id === "task-harbor-arrival")?.title).toBe("新的任务意图");
    expect(withSceneEdit.scenes.find((scene) => scene.id === "scene-harbor")?.location).toBe("新地点");
    expect(withSceneEdit.jobs).toBe(mockStoryboard.jobs);
    expect(withSceneEdit.results).toBe(mockStoryboard.results);
    expect(withSceneEdit.jobs[0].taskContentSnapshot.title).toBe("抵达仓库并发现门内异常");
  });

  it("applies explicit batch Profile, Asset, and Queue operations", () => {
    const taskIds = ["task-wall-image", "task-draft"];
    const profiled = applyProfileToTasks(mockStoryboard, taskIds, { id: "profile-h3-fast", label: "H3 · Fast Preview" });
    const bound = addAssetBindingToTasks(profiled, taskIds, { assetId: "asset-rain-audio", role: "audio" });
    const queued = queueReadyTasks(bound, taskIds, mockGenerationProfiles);

    expect(queued.snapshot.tasks.find((task) => task.id === "task-wall-image")?.state).toBe("queued");
    expect(queued.snapshot.tasks.find((task) => task.id === "task-draft")?.state).toBe("draft");
    expect(queued.queuedIds).toEqual(["task-wall-image"]);
    expect(queued.skippedIds).toEqual(["task-draft"]);
    expect(queued.snapshot.tasks.find((task) => task.id === "task-draft")?.generationProfileId).toBe("profile-h3-fast");
    expect(queued.snapshot.tasks.find((task) => task.id === "task-draft")?.assetBindings).toContainEqual({ assetId: "asset-rain-audio", role: "audio" });
    expect(queued.snapshot.jobs.at(-1)).toMatchObject({ taskId: "task-wall-image", state: "queued", providerId: "fake-video-provider" });
    expect(queued.snapshot.tasks.find((task) => task.id === "task-wall-image")?.jobIds).toContain(queued.jobIds[0]);
  });

  it("replaces current Task asset bindings without changing historical resolved asset snapshots", () => {
    const updated = replaceTaskAssetBindings(mockStoryboard, "task-hall-projector", [
      { assetId: "asset-rain-audio", role: "audio" },
    ]);

    expect(updated.tasks.find((task) => task.id === "task-hall-projector")?.assetBindings).toEqual([
      { assetId: "asset-rain-audio", role: "audio" },
    ]);
    expect(updated.jobs).toBe(mockStoryboard.jobs);
    expect(updated.jobs.find((job) => job.id === "job-projector-1")?.assetsSnapshot[0].projectRelativePath).toBe("assets/props/projector.webp");
  });
});
