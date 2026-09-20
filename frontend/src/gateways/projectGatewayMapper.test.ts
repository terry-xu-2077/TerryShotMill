import { describe, expect, it } from "vitest";
import type { PromptRevisionView, TaskEditorView } from "./projectGateway";
import { mapTaskEditor, mapWorkspaceProject } from "./projectGatewayMapper";

const revision = (id: string, day: number, prompt: string): PromptRevisionView => ({
  id, taskId: "task-1", createdAt: `2026-09-${day}T00:00:00Z`, prompt,
  sourceUserPrompt: "original", assetIds: [], includeProjectBackground: false,
  includePreviousTaskSummary: false, targetSkill: "minimax-h3", skillVersion: "1",
});
const view = (prompt: string): TaskEditorView => ({
  id: "task-1", displayNumber: 1, title: "Task", summary: "", scriptSource: "",
  userIntent: "original", userPrompt: "original", aiEnhancedPrompt: prompt,
  finalPrompt: prompt, promptSource: "ai", durationSeconds: 6,
  editorPreference: { userViewMode: "text", aiViewMode: "text" },
  generation: { resolution: "720p", quality: "standard", mode: "all", contextMode: "none" },
  assetBindings: [], revision: 2,
});

it("preserves queued video status rather than presenting it as running", () => {
  const project = mapWorkspaceProject(
    { id: "p", title: "Project", description: "", useDescriptionForAiPrompt: false },
    { project: { id: "p", title: "Project" }, runtime: { state: "running" }, tasks: [
      { id: "waiting", title: "Waiting", displayNumber: 1, status: "running",
        videoGenerationStatus: "queued", promptExcerpt: "", assetCount: 0,
        resultCount: 0, durationSeconds: 8, generationSummary: { resolution: "720p", quality: "standard" } },
    ] }, [],
  );
  expect(project.snapshot.tasks[0].state).toBe("queued");
});

describe("task editor AI history restoration", () => {
  const newest = revision("new", 20, "new prompt");
  const oldest = revision("old", 19, "old prompt");

  it("normalizes descending history without mutating the response", () => {
    const revisions = [newest, oldest];
    const task = mapTaskEditor(view("new prompt"), revisions);
    expect(task.generationParams.selectedAiPromptHistoryId).toBe("new");
    expect((task.generationParams.aiPromptHistory as Array<{ id: string }>).map((r) => r.id)).toEqual(["old", "new"]);
    expect(revisions[0]).toBe(newest);
  });

  it("restores a saved older version instead of silently selecting the newest", () => {
    expect(mapTaskEditor(view("old prompt"), [newest, oldest]).generationParams.selectedAiPromptHistoryId).toBe("old");
  });

  it("preserves saved human edits without changing immutable AI revisions", () => {
    const task = mapTaskEditor(view("edited prompt"), [newest, oldest]);
    const history = task.generationParams.aiPromptHistory as Array<{ id: string; prompt: string }>;
    const selected = history.find((r) => r.id === task.generationParams.selectedAiPromptHistoryId);
    expect(selected?.prompt).toBe("edited prompt");
    expect(history.find((r) => r.id === "new")?.prompt).toBe("new prompt");
    expect(task.promptRevisions).toHaveLength(2);
  });
});
