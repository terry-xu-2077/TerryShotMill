import { describe, expect, it } from "vitest";

import { mockGenerationProfiles } from "../../mock/generationProfiles";
import { mockStoryboard } from "../../mock/storyboard";
import {
  approveAllPendingResults,
  markTaskAndFollowingForRegeneration,
  markTaskReady,
  queueReadyTasks,
  refreshTaskContext,
  regenerateTaskAiPrompt,
  requestTaskRegeneration,
  setResultReviewState,
  setTaskPrimaryResult,
  validateTaskReadiness,
} from "./storyboardExecution";

const multiShotProfile = mockGenerationProfiles[0];

describe("Storyboard Ready, Queue, and Generation Context", () => {
  it("validates Final Prompt, Profile capability, beat timing, Context, and Provider availability", () => {
    const invalid = structuredClone(mockStoryboard);
    const task = invalid.tasks.find((item) => item.id === "task-harbor-arrival")!;
    task.finalPrompt = "";
    task.generationProfileId = "profile-h3-fast";
    task.plannedDurationSeconds = 6;
    invalid.generationContextLinks[0].stale = true;

    expect(validateTaskReadiness(invalid, task.id, mockGenerationProfiles[1], false).map((issue) => issue.code)).toEqual([
      "final-prompt",
      "profile",
      "visual-beat",
      "provider",
    ]);

    const downstreamIssues = validateTaskReadiness(invalid, "task-hall-projector", multiShotProfile, true);
    expect(downstreamIssues.map((issue) => issue.code)).toContain("context");
  });

  it("marks a valid Task Ready and keeps an invalid Task unchanged", () => {
    const valid = markTaskReady(mockStoryboard, "task-wall-image", multiShotProfile, true);
    const invalid = markTaskReady(mockStoryboard, "task-draft", multiShotProfile, true);

    expect(valid.ready).toBe(true);
    expect(valid.snapshot.tasks.find((task) => task.id === "task-wall-image")?.state).toBe("ready");
    expect(invalid.ready).toBe(false);
    expect(invalid.snapshot).toBe(mockStoryboard);
    expect(invalid.issues.map((issue) => issue.code)).toEqual(["final-prompt", "duration"]);
  });

  it("queues one Task by appending an immutable Job snapshot without rewriting older Jobs or Results", () => {
    const queued = queueReadyTasks(mockStoryboard, ["task-wall-image"], mockGenerationProfiles, "2026-09-12T12:00:00.000Z");
    const job = queued.snapshot.jobs.at(-1)!;

    expect(queued.jobIds).toEqual([job.id]);
    expect(job).toMatchObject({ taskId: "task-wall-image", state: "queued", finalPromptSnapshot: mockStoryboard.tasks[2].finalPrompt });
    expect(job.taskContentSnapshot.visualBeats).toHaveLength(1);
    expect(job.generationProfileSnapshot.capability.multiShotPrompt).toBe(true);
    expect(queued.snapshot.jobs.slice(0, -1)).toEqual(mockStoryboard.jobs);
    expect(queued.snapshot.results).toBe(mockStoryboard.results);
  });

  it("refreshes a stale incoming Context Link from the upstream Primary Result", () => {
    const stale = structuredClone(mockStoryboard);
    stale.generationContextLinks[0].stale = true;
    stale.generationContextLinks[0].sourceResultId = undefined;

    const refreshed = refreshTaskContext(stale, "task-hall-projector");

    expect(refreshed.refreshedLinkIds).toEqual(["context-arrival-projector"]);
    expect(refreshed.snapshot.generationContextLinks[0]).toMatchObject({ stale: false, sourceResultId: "result-arrival-1" });
  });

  it("regenerates only AI Prompt and preserves manual Final Prompt plus immutable history", () => {
    const originalFinal = mockStoryboard.tasks[2].finalPrompt;
    const regenerated = regenerateTaskAiPrompt(mockStoryboard, "task-wall-image");
    const task = regenerated.tasks.find((item) => item.id === "task-wall-image")!;

    expect(task.aiPrompt).toContain("Mock AI Prompt Revision 1");
    expect(task.finalPrompt).toBe(originalFinal);
    expect(task.promptRevisions).toHaveLength(1);
    expect(regenerated.jobs).toBe(mockStoryboard.jobs);
    expect(regenerated.results).toBe(mockStoryboard.results);
  });

  it("marks the selected Task and following story Tasks for explicit regeneration without deleting history", () => {
    const result = markTaskAndFollowingForRegeneration(mockStoryboard, "task-wall-image");

    expect(result.affectedTaskIds).toEqual(["task-wall-image", "task-voice", "task-corridor", "task-draft"]);
    expect(result.snapshot.tasks.find((task) => task.id === "task-wall-image")?.state).toBe("draft");
    expect(result.snapshot.tasks.find((task) => task.id === "task-voice")?.state).toBe("context-stale");
    expect(result.snapshot.jobs).toBe(mockStoryboard.jobs);
    expect(result.snapshot.results).toBe(mockStoryboard.results);
  });

  it("marks downstream Context stale when an upstream Primary Result changes", () => {
    const withAlternative = structuredClone(mockStoryboard);
    withAlternative.results.push({
      id: "result-arrival-2",
      jobId: "job-arrival-1",
      videoUrl: "results/result-arrival-2.mp4",
      metadata: { durationSeconds: 15 },
      reviewState: "approved",
    });

    const changed = setTaskPrimaryResult(withAlternative, "task-harbor-arrival", "result-arrival-2");

    expect(changed.changed).toBe(true);
    expect(changed.snapshot.tasks.find((task) => task.id === "task-harbor-arrival")?.primaryResultId).toBe("result-arrival-2");
    expect(changed.staleContextLinkIds).toEqual(["context-arrival-projector"]);
    expect(changed.snapshot.generationContextLinks[0]).toMatchObject({ sourceResultId: "result-arrival-1", stale: true });
  });

  it("reviews Results and requests regeneration without deleting immutable history", () => {
    const rejected = setResultReviewState(mockStoryboard, "result-arrival-2", "rejected");
    const approved = approveAllPendingResults(mockStoryboard);
    const regenerated = requestTaskRegeneration(rejected, "task-harbor-arrival");

    expect(rejected.results.find((result) => result.id === "result-arrival-2")?.reviewState).toBe("rejected");
    expect(approved.approvedResultIds).toEqual(["result-arrival-2"]);
    expect(approved.snapshot.results.find((result) => result.id === "result-arrival-2")?.reviewState).toBe("approved");
    expect(regenerated.tasks.find((task) => task.id === "task-harbor-arrival")?.state).toBe("ready");
    expect(regenerated.jobs).toBe(rejected.jobs);
    expect(regenerated.results).toBe(rejected.results);
  });
});
