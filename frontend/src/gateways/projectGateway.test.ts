import { afterEach, describe, expect, it, vi } from "vitest";

import { HttpProjectGateway, ProjectGatewayError } from "./projectGateway";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HttpProjectGateway", () => {
  it("serializes rapid preference switches and waits for them before reopening the task", async () => {
    let releaseFirst!: () => void;
    const firstRequest = new Promise<void>(resolve => { releaseFirst = resolve; });
    let preference = { userViewMode: "visual", aiViewMode: "visual" };
    let writes = 0;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/editor-preference")) {
        if (++writes === 1) await firstRequest;
        preference = { ...preference, ...JSON.parse(String(init?.body)) };
        return new Response(JSON.stringify(preference));
      }
      return new Response(JSON.stringify({ editorPreference: preference }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const gateway = new HttpProjectGateway();
    const first = gateway.updateEditorPreference("p", "t", { userViewMode: "text" });
    const second = gateway.updateEditorPreference("p", "t", { userViewMode: "visual", aiViewMode: "text" });
    const reopened = gateway.getTaskEditor("p", "t");
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    releaseFirst();
    await Promise.all([first, second]);
    expect((await reopened).editorPreference).toEqual({ userViewMode: "visual", aiViewMode: "text" });
    expect(fetchMock.mock.calls.map(([url]) => url.split("/").at(-1))).toEqual(["editor-preference", "editor-preference", "editor"]);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ userViewMode: "text" });
  });

  it("keeps the backend /api/v1 route and unwraps project lists", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => new Response(JSON.stringify({
      items: [{
        id: "project-1",
        title: "异星边境",
        status: "idle",
        taskCount: 0,
        assetCount: 0,
        updatedAt: "2026-09-13T00:00:00Z",
      }],
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const projects = await new HttpProjectGateway().listProjects();

    expect(fetchMock).toHaveBeenCalledWith("/api/v1/projects", undefined);
    expect(projects[0]).toMatchObject({ id: "project-1", title: "异星边境" });
  });

  it("translates prompt enhancement input to the backend contract", async () => {
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url.endsWith("/editor")) {
        return new Response(JSON.stringify({ revision: 4 }), { status: 200 });
      }
      return new Response(JSON.stringify({
        id: "revision-1",
        taskId: "task-1",
        createdAt: "2026-09-13T00:00:00Z",
        prompt: "增强后的提示词",
        sourceUserPrompt: "原始提示词",
        assetIds: ["asset-1"],
        includeProjectBackground: true,
        includePreviousTaskSummary: true,
        targetSkill: "minimax-h3",
        skillVersion: "1",
      }), { status: 201 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await new HttpProjectGateway().enhancePrompt("project-1", {
      taskId: "task-1",
      isDraft: false,
      userPrompt: "原始提示词",
      previousTaskSummary: "上一任务",
      projectBackground: "项目背景",
      assets: [{
        id: "asset-1",
        name: "主角",
        reference: "<Subject 1>",
        kind: "subject",
      }],
      generation: {
        resolution: "1080p",
        quality: "标准",
        mode: "全能参考",
        durationSeconds: 6,
        contextMode: "片段承接",
      },
    });

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/projects/project-1/tasks/task-1/prompt-enhancements",
    );
    expect(JSON.parse(String(init.body))).toMatchObject({
      target: "minimax-h3",
      userPrompt: "原始提示词",
      media: [{ assetId: "asset-1", reference: "<Subject 1>", role: "subject" }],
      context: { includeProjectBackground: true, includePreviousTaskSummary: true },
    });
    expect(result).toEqual({
      id: "revision-1",
      createdAt: "2026-09-13T00:00:00Z",
      prompt: "增强后的提示词",
      taskRevision: 4,
    });
  });

  it("uses the non-persistent preview endpoint for a new task draft", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => new Response(JSON.stringify({
      previewId: "preview-1",
      createdAt: "2026-09-14T00:00:00Z",
      prompt: "草稿增强结果",
      targetSkill: "minimax-h3",
      skillVersion: "1",
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await new HttpProjectGateway().enhancePrompt("project-1", {
      taskId: "task-local-1",
      isDraft: true,
      previousTaskId: "task-previous",
      userPrompt: "草稿提示词",
      previousTaskSummary: "上一任务",
      assets: [],
      generation: {
        resolution: "1080p",
        quality: "标准",
        mode: "全能参考",
        durationSeconds: 6,
        contextMode: "片段承接",
      },
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/projects/project-1/prompt-enhancement-previews",
    );
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toMatchObject({
      previousTaskId: "task-previous",
      userPrompt: "草稿提示词",
      context: { includePreviousTaskSummary: true },
    });
    expect(result).toEqual({
      id: "preview-1",
      createdAt: "2026-09-14T00:00:00Z",
      prompt: "草稿增强结果",
    });
  });

  it("maps the backend originalFileName field and project media route", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ items: [{
      id: "asset-1",
      name: "林澜",
      originalFileName: "linlan.png",
      projectRelativePath: "assets/asset-1.png",
      mediaType: "image",
      category: "character",
      tags: ["主角"],
    }] }), { status: 200 })));

    const assets = await new HttpProjectGateway().listAssets("project-1");

    expect(assets[0]).toMatchObject({
      originalFilename: "linlan.png",
      mediaUrl: "/media/project-1/assets/asset-1.png",
    });
  });

  it("subscribes to named project runtime events and closes cleanly", () => {
    const listeners = new Map<string, EventListener>();
    const close = vi.fn();
    const EventSourceMock = vi.fn(function (this: { addEventListener: (name: string, listener: EventListener) => void; close: () => void }) {
      this.addEventListener = (name, listener) => listeners.set(name, listener);
      this.close = close;
    });
    vi.stubGlobal("EventSource", EventSourceMock);
    const listener = vi.fn();

    const unsubscribe = new HttpProjectGateway().subscribeProject("project-1", listener);
    listeners.get("task.status_changed")?.(new MessageEvent("task.status_changed", {
      data: JSON.stringify({
        type: "task.status_changed",
        projectId: "project-1",
        taskId: "task-1",
        status: "running",
        progress: 20,
      }),
    }));
    unsubscribe();

    expect(EventSourceMock).toHaveBeenCalledWith("/api/v1/projects/project-1/events");
    expect(listener).toHaveBeenCalledWith(expect.objectContaining({
      type: "task.status_changed",
      taskId: "task-1",
      progress: 20,
    }));
    expect(close).toHaveBeenCalledOnce();
  });

  it("preserves stable backend error codes", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      error: { code: "TASK_CONFLICT", message: "任务已被更新", details: { revision: 3 } },
    }), { status: 409 })));

    await expect(new HttpProjectGateway().getTaskEditor("project-1", "task-1"))
      .rejects.toEqual(expect.objectContaining<ProjectGatewayError>({
        name: "ProjectGatewayError",
        code: "TASK_CONFLICT",
        status: 409,
        message: "任务已在别处更新，请重新打开后再保存。",
      }));
  });
});
