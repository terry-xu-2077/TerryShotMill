import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createTask, importImage } from "./helpers";

test("multiple timelines keep separate clips and share the project asset pool", async ({ page }) => {
  const title = `多时间线 ${Date.now()}`;
  const path = `${process.env.SHOTMILL_DATA_ROOT}\\multi-timeline-${Date.now()}.shotmill`;
  const created = await page.request.post("/api/v1/projects", { data: { title, path } });
  expect(created.ok()).toBeTruthy();
  const projectId = (await created.json()).id as string;
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  await expect(page.getByRole("heading", { name: "时间线" })).toBeVisible();
  await page.getByRole("button", { name: "新建时间线" }).click();
  await page.getByRole("button", { name: "重命名 时间线 1" }).click();
  await page.getByPlaceholder("时间线名称").fill("开场");
  await page.getByRole("button", { name: "保存" }).click();
  await page.getByRole("button", { name: /开场.*0 个片段/ }).click();
  const frame = page.frameLocator('iframe[title="TerryDirector 导演时间线"]');
  await page.getByRole("button", { name: "新建片段" }).click();
  await frame.getByRole("textbox", { name: "片段名称" }).fill("片段 A");
  await frame.locator("#fileInput").setInputFiles("src-tauri/icons/StoreLogo.png");
  await expect(frame.getByRole("region", { name: "资产池" })).toContainText("StoreLogo");
  await expect.poll(async () => (await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json()).tasks.length).toBe(1);
  await page.getByRole("button", { name: "时间线列表" }).click();
  await page.getByRole("button", { name: "新建时间线" }).click();
  await page.getByRole("button", { name: "重命名 时间线 2" }).click();
  await page.getByPlaceholder("时间线名称").fill("结尾");
  await page.getByRole("button", { name: "保存" }).click();
  await page.getByRole("button", { name: /结尾.*0 个片段/ }).click();
  await expect(frame.getByRole("region", { name: "资产池" })).toContainText("StoreLogo");
  await expect(frame.getByRole("textbox", { name: "片段名称" })).toHaveCount(0);
  await page.getByRole("button", { name: "新建片段" }).click();
  await frame.getByRole("textbox", { name: "片段名称" }).fill("片段 B");
  await expect.poll(async () => {
    const workspace = await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json();
    return workspace.timelines.map((item: { taskIds: string[] }) => item.taskIds.length);
  }).toEqual([1, 1]);
  await page.reload();
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  await expect(page.getByRole("heading", { name: "结尾" })).toBeVisible();
  await expect(page.frameLocator('iframe[title="TerryDirector 导演时间线"]').getByRole("textbox", { name: "片段名称" })).toHaveValue("片段 B");
  await page.getByRole("button", { name: "时间线列表" }).click();
  await expect(page.getByRole("button", { name: /开场.*1 个片段/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /结尾.*1 个片段/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "任务视图" })).toHaveCount(0);
});

test("timeline preview follows seeking, click playback and Space without video controls", async ({ page }, testInfo) => {
  const title = `时间线预览 ${Date.now()}`;
  const path = `${process.env.SHOTMILL_DATA_ROOT}\\director-preview-${Date.now()}.shotmill`;
  const created = await page.request.post("/api/v1/projects", { data: { title, path } });
  expect(created.ok()).toBeTruthy();
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  await page.getByRole("button", { name: "新建时间线" }).click();
  await page.getByRole("button", { name: /时间线 1.*打开时间线/ }).click();
  await page.getByRole("button", { name: "新建片段" }).click();
  const preview = page.getByLabel("时间线视频预览");
  const frame = page.frameLocator('iframe[title="TerryDirector 导演时间线"]');
  await expect(preview.getByRole("button", { name: "播放时间线" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("timeline-preview-layout.png") });
  await expect(preview.locator("video[controls]")).toHaveCount(0);
  await preview.getByRole("button", { name: "播放时间线" }).click();
  await expect(preview.getByRole("button", { name: "暂停时间线播放" })).toBeVisible();
  await frame.locator("#timelineBody").click({ position: { x: 130, y: 85 } });
  await expect(preview.getByRole("button", { name: "播放时间线" })).toBeVisible();
  await frame.locator("body").press("Space");
  await expect(preview.getByRole("button", { name: "暂停时间线播放" })).toBeVisible();
  await frame.locator("body").press("Space");
  await expect(preview.getByRole("button", { name: "播放时间线" })).toBeVisible();
  await frame.locator("body").evaluate(() => (window as unknown as { TerryDirectorDemo: { timeline: { setFrame: (frame: number) => void } } }).TerryDirectorDemo.timeline.setFrame(24));
  await expect(preview).toHaveAttribute("data-frame", "24");
  await frame.getByRole("button", { name: "切换提示词显示方式" }).click();
  await frame.getByRole("textbox", { name: "当前片段提示词" }).fill("预览切换后仍保留这段提示词。");
  await page.getByRole("button", { name: "生成结果" }).click();
  await expect(page.getByRole("heading", { name: "生成结果" })).toBeVisible();
  await page.getByRole("button", { name: "时间线 1", exact: true }).click();
  await frame.getByRole("button", { name: "切换提示词显示方式" }).click();
  await expect(frame.getByRole("textbox", { name: "当前片段提示词" })).toHaveValue("预览切换后仍保留这段提示词。");
});

test("embedded director follows light, dark and custom palette without reloading the editor", async ({ page }, testInfo) => {
  const title = `时间线主题 ${Date.now()}`;
  const path = `${process.env.SHOTMILL_DATA_ROOT}\\director-theme-${Date.now()}.shotmill`;
  const created = await page.request.post("/api/v1/projects", { data: { title, path } });
  expect(created.ok()).toBeTruthy();
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  await page.getByRole("button", { name: "新建时间线" }).click();
  await page.getByRole("button", { name: "重命名 时间线 1" }).click();
  await page.getByPlaceholder("时间线名称").fill("主题预览");
  await page.getByRole("button", { name: "保存" }).click();
  await page.getByRole("button", { name: /主题预览.*0 个片段/ }).click();
  await page.getByRole("button", { name: "新建片段" }).click();
  const frame = page.frameLocator('iframe[title="TerryDirector 导演时间线"]');
  const switcher = page.getByRole("group", { name: "界面主题" });
  await switcher.getByRole("button", { name: "亮色" }).click();
  await expect(frame.locator("body")).toHaveAttribute("data-shotmill-mode", "light");
  const light = await frame.locator(".timeline-panel").evaluate(element => getComputedStyle(element).backgroundColor);
  await frame.locator("body").evaluate(element => { element.dataset.themeProbe = "kept"; });
  await page.waitForTimeout(300);
  await page.screenshot({ path: testInfo.outputPath("director-light.png") });
  await switcher.getByRole("button", { name: "暗色" }).click();
  await expect(frame.locator("body")).toHaveAttribute("data-shotmill-mode", "dark");
  await expect(frame.locator("body")).toHaveAttribute("data-theme-probe", "kept");
  const dark = await frame.locator(".timeline-panel").evaluate(element => getComputedStyle(element).backgroundColor);
  expect(dark).not.toBe(light);
  const accentBefore = await frame.locator("#zoomRange").evaluate(element => getComputedStyle(element).accentColor);
  await page.waitForTimeout(300);
  await page.screenshot({ path: testInfo.outputPath("director-dark.png") });
  await page.evaluate(() => {
    const palette = {
      base: "#151618", accent: "#d06b75", effect: "#e9a36e", text: "#dce0e5", textBright: "#f7fafc",
    };
    localStorage.setItem("shotmill.palette.dark", JSON.stringify(palette));
    for (const [key, value] of Object.entries(palette))
      document.documentElement.style.setProperty(`--tc-${key === "textBright" ? "text-bright" : key === "text" ? "text-main" : key}`, value);
    window.dispatchEvent(new Event("shotmill-palette-change"));
  });
  await expect(frame.locator("body")).toHaveCSS("--shotmill-accent", "#d06b75");
  await expect(page.locator(".director-duration strong")).toHaveCSS("color", "rgb(208, 107, 117)");
  const accentAfter = await frame.locator("#zoomRange").evaluate(element => getComputedStyle(element).accentColor);
  expect(accentAfter).not.toBe(accentBefore);
  await expect(frame.locator("body")).toHaveAttribute("data-theme-probe", "kept");
  await page.waitForTimeout(300);
  await page.screenshot({ path: testInfo.outputPath("director-custom.png") });
  await switcher.getByRole("button", { name: "亮色" }).click();
  await expect(frame.locator("body")).toHaveAttribute("data-shotmill-mode", "light");
  await page.evaluate(() => {
    const palette = {
      base: "#68717b", accent: "#237b70", effect: "#519b88", text: "#25282e", textBright: "#111318",
    };
    localStorage.setItem("shotmill.palette.light", JSON.stringify(palette));
    for (const [key, value] of Object.entries(palette))
      document.documentElement.style.setProperty(`--tc-${key === "textBright" ? "text-bright" : key === "text" ? "text-main" : key}`, value);
    window.dispatchEvent(new Event("shotmill-palette-change"));
  });
  await expect(frame.locator("body")).toHaveCSS("--shotmill-accent", "#237b70");
  await expect(page.locator(".director-duration strong")).toHaveCSS("color", "rgb(35, 123, 112)");
  await expect(frame.locator("body")).toHaveAttribute("data-theme-probe", "kept");
  await page.waitForTimeout(300);
  await page.screenshot({ path: testInfo.outputPath("director-custom-light.png") });
});

test("TerryDirector editor creates and edits a clip inline, then reopens it from the project file", async ({ page }, testInfo) => {
  const title = `时间线 ${Date.now()}`;
  const path = `${process.env.SHOTMILL_DATA_ROOT}\\director-timeline-${Date.now()}.shotmill`;
  const created = await page.request.post("/api/v1/projects", { data: { title, path } });
  expect(created.ok()).toBeTruthy();
  const projectId = (await created.json()).id as string;
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  await page.getByRole("button", { name: "新建时间线" }).click();
  await page.getByRole("button", { name: "重命名 时间线 1" }).click();
  await page.getByPlaceholder("时间线名称").fill("第一条时间线");
  await page.getByRole("button", { name: "保存" }).click();
  await page.getByRole("button", { name: /第一条时间线.*0 个片段/ }).click();
  const frame = page.frameLocator('iframe[title="TerryDirector 导演时间线"]');
  await expect(frame.getByRole("region", { name: "资产池" })).toBeVisible();
  await expect(frame.getByRole("region", { name: "提示词编辑" })).toBeVisible();
  await expect(frame.getByRole("region", { name: "时间轴" })).toBeVisible();
  await expect(frame.locator("#app > .topbar")).toBeHidden();
  const heading = page.locator(".task-collection-heading.is-director");
  await expect(heading.getByRole("button", { name: "新建片段" })).toBeVisible();
  await expect(heading.getByRole("button", { name: "全局提示词" })).toBeVisible();
  await expect(heading.getByRole("button", { name: "一键增强所有提示词" })).toBeVisible();
  await expect(heading.getByText("生成前自动 AI 增强提示词")).toHaveCount(0);
  const titleBox = await heading.getByRole("heading", { name: "第一条时间线" }).boundingBox();
  const create = await heading.getByRole("button", { name: "新建片段" }).boundingBox();
  const duration = await heading.locator(".director-duration").boundingBox();
  expect(titleBox && create && duration).toBeTruthy();
  expect(create!.x).toBeGreaterThan(titleBox!.x + titleBox!.width);
  expect(Math.abs(create!.y - titleBox!.y)).toBeLessThan(8);
  expect(duration!.x).toBeGreaterThan(create!.x + create!.width);
  await expect(frame.getByText("TerryDirector", { exact: true })).toBeHidden();
  await expect(frame.getByRole("button", { name: "保存工程" })).toBeHidden();
  await expect(page.getByRole("button", { name: "导入" })).toBeVisible();
  await expect(page.getByRole("button", { name: "导出" })).toBeVisible();
  await page.getByRole("button", { name: "新建片段" }).click();
  await frame.getByRole("textbox", { name: "片段名称" }).fill("第一场");
  await frame.getByRole("button", { name: "切换提示词显示方式" }).click();
  await frame.getByRole("textbox", { name: "当前片段提示词" }).fill("角色穿过雨夜码头，走入仓库。");
  await expect(page.getByRole("dialog", { name: /任务/ })).toHaveCount(0);
  await expect(page.locator(".director-duration")).toContainText("00:00:10:00");
  const painted = await frame.locator(".timeline-canvas.content").evaluate(canvas => {
    const element = canvas as HTMLCanvasElement;
    return element.width > 1 && element.height > 1 && element.toDataURL().length > 5000;
  });
  expect(painted).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath("director-timeline.png") });
  await expect.poll(async () => (await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json()).tasks.length).toBe(1);
  const workspace = await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json();
  const savedId = workspace.tasks[0].id as string;
  const editor = await (await page.request.get(`/api/v1/projects/${projectId}/tasks/${savedId}/editor`)).json();
  expect(editor.userPrompt).toContain("角色穿过雨夜码头");
  await frame.locator("#fileInput").setInputFiles("src-tauri/icons/StoreLogo.png");
  await expect(frame.getByRole("region", { name: "资产池" })).toContainText("StoreLogo");
  await expect.poll(async () => (await (await page.request.get(`/api/v1/projects/${projectId}/assets`)).json()).items.length).toBe(1);
  const downloadReady = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出" }).click();
  expect((await downloadReady).suggestedFilename()).toBe("TerryDirector-timeline.json");
  await page.getByRole("button", { name: "时间线列表" }).click();
  await expect(page.locator(".task-list-row").filter({ hasText: "第一条时间线" })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  await page.getByRole("button", { name: /第一条时间线.*1 个片段/ }).click();
  const reopened = page.frameLocator('iframe[title="TerryDirector 导演时间线"]');
  await expect(reopened.getByRole("textbox", { name: "片段名称" })).toHaveValue("第一场");
  await expect(reopened.getByRole("region", { name: "资产池" })).toContainText("StoreLogo");
  await reopened.getByRole("button", { name: "切换提示词显示方式" }).click();
  await expect(reopened.getByRole("textbox", { name: "当前片段提示词" })).toHaveValue("角色穿过雨夜码头，走入仓库。");
});

test("TerryDirector drag and trim persist after a failed save is retried", async ({ page }) => {
  const title = `编排 ${Date.now()}`;
  const path = `${process.env.SHOTMILL_DATA_ROOT}\\arrangement-${Date.now()}.shotmill`;
  const created = await page.request.post("/api/v1/projects", { data: { title, path } });
  expect(created.ok()).toBeTruthy();
  const projectId = (await created.json()).id as string;
  await createTask(page, projectId, "第一场");
  const secondTask = await createTask(page, projectId, "第二场");
  await createTask(page, projectId, "第三场");
  let failOnce = true;
  await page.route(`**/tasks/${secondTask.id}/timeline`, async route => {
    if (failOnce) {
      failOnce = false;
      await route.fulfill({ status: 503, json: { detail: "临时写入失败" } });
    } else await route.continue();
  });

  await page.goto("/dev/ui");
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  const frame = page.frameLocator('iframe[title="TerryDirector 导演时间线"]');
  const canvas = frame.locator(".timeline-canvas.overlay");
  await expect(canvas).toBeVisible();
  await expect.poll(() => canvas.evaluate(() => (window as any).TerryDirectorDemo.getState().clips.length)).toBe(3);
  const geometry = await canvas.evaluate(() => {
    const director = (window as any).TerryDirectorDemo;
    const clip = director.getState().clips[1];
    const timeline = director.timeline;
    return { middle: timeline.x((clip.start + clip.end) / 2), right: timeline.x(clip.end),
      y: timeline.y() + timeline.trackHeight / 2 };
  });
  const bounds = (await canvas.boundingBox())!;
  const x = bounds.x + geometry.middle, y = bounds.y + geometry.y;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 65, y, { steps: 8 });
  await page.mouse.up();
  await expect(page.locator(".director-save-error")).toContainText(/503|保存失败/);
  const draftStart = await canvas.evaluate(() => (window as any).TerryDirectorDemo.getState().clips[1].start);
  expect(draftStart).toBeGreaterThan(6 * 24);
  await page.getByRole("button", { name: "重试保存" }).click();
  const workspaceUrl = `/api/v1/projects/${projectId}/workspace`;
  await expect.poll(async () => {
    const workspace = await (await page.request.get(workspaceUrl)).json();
    return workspace.tasks.find((task: { id: string }) => task.id === secondTask.id).timelineStartSeconds as number;
  }).toBeGreaterThan(6);
  const trim = await canvas.evaluate(() => {
    const director = (window as any).TerryDirectorDemo;
    const clip = director.getState().clips[1];
    return { right: director.timeline.x(clip.end), y: director.timeline.y() + director.timeline.trackHeight / 2 };
  });
  const afterMoveBounds = (await canvas.boundingBox())!;
  await page.mouse.move(afterMoveBounds.x + trim.right - 3, afterMoveBounds.y + trim.y);
  await page.mouse.down();
  await page.mouse.move(afterMoveBounds.x + trim.right + 45, afterMoveBounds.y + trim.y, { steps: 8 });
  await page.mouse.up();
  await expect.poll(async () => {
    const workspace = await (await page.request.get(workspaceUrl)).json();
    return workspace.tasks.find((task: { id: string }) => task.id === secondTask.id).durationSeconds as number;
  }).toBeGreaterThan(6);
  await page.getByRole("button", { name: "返回项目首页" }).click();
  await page.reload();
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  const reopened = page.frameLocator('iframe[title="TerryDirector 导演时间线"]');
  await expect.poll(() => reopened.locator(".timeline-canvas.overlay").evaluate(() => (window as any).TerryDirectorDemo.getState().clips.length)).toBe(3);
  await expect.poll(async () => reopened.locator(".timeline-canvas.overlay").evaluate(() => {
    const clip = (window as any).TerryDirectorDemo.getState().clips[1];
    return { start: clip.start, duration: clip.end - clip.start };
  })).toMatchObject({ start: draftStart, duration: expect.any(Number) });
});

test("import keeps offline assets and relinking restores every prompt reference", async ({ page }) => {
  const title = `离线素材 ${Date.now()}`;
  const path = `${process.env.SHOTMILL_DATA_ROOT}\\offline-assets-${Date.now()}.shotmill`;
  const created = await page.request.post("/api/v1/projects", { data: { title, path } });
  expect(created.ok()).toBeTruthy();
  const projectId = (await created.json()).id as string;
  const imported = { format: "terrydirector-timeline", version: 1, document: {
    version: 2, fps: 24, selected: "clip-1", globalPrompt: "", aiGlobalPrompt: "",
    globalPromptMode: "user", globalAiMetadata: {}, autoAiEnhance: false,
    clips: [{ id: "clip-1", name: "离线片段", start: 0, end: 120,
      prompt: "<Picture 1> 穿过雨夜，经过 <Picture 2>。", aiPrompt: "", promptMode: "user", refs: ["legacy-picture", "legacy-background"],
      useGlobalPrompt: false, transitionMode: "tail_reference", suspended: false, aiOptOut: false, aiMetadata: {} }],
    assets: [{ id: "legacy-picture", name: "原始画面.png", kind: "image", number: 1,
      source: { type: "comfy-input", path: "原始画面.png" } },
    { id: "legacy-background", name: "背景图.png", kind: "image", number: 2,
      source: { type: "comfy-input", path: "背景图.png" } }],
  } };
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  await page.getByRole("button", { name: "新建时间线" }).click();
  await page.getByRole("button", { name: "重命名 时间线 1" }).click();
  await page.getByPlaceholder("时间线名称").fill("离线测试");
  await page.getByRole("button", { name: "保存" }).click();
  await page.getByRole("button", { name: /离线测试.*0 个片段/ }).click();
  const frame = page.frameLocator('iframe[title="TerryDirector 导演时间线"]');
  await frame.locator("#timelineImportInput").setInputFiles({
    name: "timeline.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(imported)),
  });
  await expect(frame.locator("#missingCount")).toContainText("2 个待重新链接");
  await expect.poll(async () => (await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json()).tasks.length).toBe(1);
  await expect.poll(async () => (await (await page.request.get(`/api/v1/projects/${projectId}/settings`)).json()).director.unresolvedAssets?.length).toBe(2);
  await expect(page.locator(".director-save-error")).toHaveCount(0);
  await page.reload();
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  const reopened = page.frameLocator('iframe[title="TerryDirector 导演时间线"]');
  await expect(reopened.locator("#missingCount")).toContainText("2 个待重新链接");
  const taskId = ((await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json()).tasks[0].id) as string;
  const before = await (await page.request.get(`/api/v1/projects/${projectId}/tasks/${taskId}/editor`)).json();
  expect(before.userPrompt).toContain("<Picture 1>");
  expect(before.assetBindings).toHaveLength(0);
  const fileChooser = page.waitForEvent("filechooser");
  await reopened.locator('[data-relink-asset="legacy-picture"]').last().click();
  const image = readFileSync("src-tauri/icons/StoreLogo.png");
  await (await fileChooser).setFiles([
    { name: "原始画面.png", mimeType: "image/png", buffer: image },
    { name: "背景图.png", mimeType: "image/png", buffer: image },
  ]);
  await expect(reopened.locator("#missingCount")).toBeHidden();
  await expect.poll(async () => {
    const editor = await (await page.request.get(`/api/v1/projects/${projectId}/tasks/${taskId}/editor`)).json();
    return editor.assetBindings.length;
  }).toBe(2);
  const after = await (await page.request.get(`/api/v1/projects/${projectId}/tasks/${taskId}/editor`)).json();
  expect(after.userPrompt).toContain("<Picture 1>");
  expect(after.userPrompt).toContain("<Picture 2>");
  await expect.poll(async () => (await (await page.request.get(`/api/v1/projects/${projectId}/settings`)).json()).director.unresolvedAssets?.length).toBe(0);
  await page.reload();
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  await expect(page.frameLocator('iframe[title="TerryDirector 导演时间线"]').locator("#missingCount")).toBeHidden();
});

test("desktop relink uses the selected local file and keeps its original bytes in place", async ({ page }) => {
  const source = resolve("src-tauri/icons/StoreLogo.png");
  await page.addInitScript(({ localPath }) => {
    (window as any).isTauri = true;
    (window as any).__TAURI_INTERNALS__ = { invoke: async (command: string) =>
      command === "choose_asset_files" ? [localPath] : [] };
  }, { localPath: source });
  const title = `本地重链 ${Date.now()}`;
  const path = `${process.env.SHOTMILL_DATA_ROOT}\\local-relink-${Date.now()}.shotmill`;
  const created = await page.request.post("/api/v1/projects", { data: { title, path } });
  const projectId = (await created.json()).id as string;
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  await page.getByRole("button", { name: "新建时间线" }).click();
  await page.getByRole("button", { name: "重命名 时间线 1" }).click();
  await page.getByPlaceholder("时间线名称").fill("重链测试");
  await page.getByRole("button", { name: "保存" }).click();
  await page.getByRole("button", { name: /重链测试.*0 个片段/ }).click();
  const frame = page.frameLocator('iframe[title="TerryDirector 导演时间线"]');
  await frame.locator("#timelineImportInput").setInputFiles({
    name: "timeline.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify({
      format: "terrydirector-timeline", version: 1, document: {
        version: 2, fps: 24, selected: "clip-1", globalPrompt: "", aiGlobalPrompt: "",
        globalPromptMode: "user", globalAiMetadata: {}, autoAiEnhance: false,
        clips: [{ id: "clip-1", name: "测试片段", start: 0, end: 120,
          prompt: "<Picture 1> 画面", aiPrompt: "", promptMode: "user", refs: ["offline-image"],
          useGlobalPrompt: false, transitionMode: "tail_reference", suspended: false, aiOptOut: false, aiMetadata: {} }],
        assets: [{ id: "offline-image", name: "原文件.png", kind: "image", number: 1,
          source: { type: "comfy-input", path: "原文件.png" } }],
      },
    })),
  });
  await expect(frame.locator("#missingCount")).toContainText("1 个待重新链接");
  await expect.poll(async () => (await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json()).tasks.length).toBe(1);
  await expect.poll(async () => (await (await page.request.get(`/api/v1/projects/${projectId}/settings`)).json()).director.unresolvedAssets?.length).toBe(1);
  await frame.locator('[data-relink-asset="offline-image"]').last().click();
  await expect(frame.locator("#missingCount")).toBeHidden();
  await expect.poll(async () => (await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json()).tasks.length).toBe(1);
  const workspace = await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json();
  await expect.poll(async () => {
    const editor = await (await page.request.get(`/api/v1/projects/${projectId}/tasks/${workspace.tasks[0].id}/editor`)).json();
    return editor.assetBindings.length;
  }, { timeout: 15000 }).toBe(1);
  await expect.poll(async () => (await (await page.request.get(`/api/v1/projects/${projectId}/settings`)).json()).director.unresolvedAssets?.length).toBe(0);
  await expect(page.locator(".director-save-error")).toHaveCount(0);
  await page.reload();
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  await expect(page.frameLocator('iframe[title="TerryDirector 导演时间线"]').locator("#missingCount")).toBeHidden();
  expect(readFileSync(source).length).toBeGreaterThan(0);
});

test("provided TerryDirector timeline retains its clips and offline asset placeholders", async ({ page }, testInfo) => {
  const fixture = process.env.SHOTMILL_DIRECTOR_IMPORT_FIXTURE;
  test.skip(!fixture, "Set SHOTMILL_DIRECTOR_IMPORT_FIXTURE to a local TerryDirector JSON file");
  const title = `导入验收 ${Date.now()}`;
  const path = `${process.env.SHOTMILL_DATA_ROOT}\\provided-timeline-${Date.now()}.shotmill`;
  const created = await page.request.post("/api/v1/projects", { data: { title, path } });
  expect(created.ok()).toBeTruthy();
  const projectId = (await created.json()).id as string;
  const existingAsset = await importImage(page, projectId, "既有项目素材");
  const existingTask = await page.request.post(`/api/v1/projects/${projectId}/tasks`, { data: {
    title: "导入前的任务", userPrompt: "<Picture 1> 原有画面", promptSource: "user",
    durationSeconds: 4, assetBindings: [{ assetId: existingAsset.id, reference: "<Picture 1>" }],
  } });
  expect(existingTask.ok()).toBeTruthy();
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  const frame = page.frameLocator('iframe[title="TerryDirector 导演时间线"]');
  await frame.locator("#timelineImportInput").setInputFiles(fixture!);
  await page.getByRole("dialog", { name: "导入时间线" }).getByRole("button", { name: "确认导入" }).click();
  await expect(frame.locator("#missingCount")).toContainText("7 个待重新链接");
  await expect(frame.locator("#refCount")).toHaveText("8");
  await expect.poll(async () => (await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json()).tasks.length).toBe(9);
  await expect.poll(async () => (await (await page.request.get(`/api/v1/projects/${projectId}/settings`)).json()).director.unresolvedAssets?.length,
    { timeout: 20000 }).toBe(7);
  await expect(page.locator(".director-save-error")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("imported-offline-assets.png") });
  expect((await (await page.request.get(`/api/v1/projects/${projectId}/assets`)).json()).items
    .some((asset: { id: string }) => asset.id === existingAsset.id)).toBeTruthy();
  await page.reload();
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  const reopened = page.frameLocator('iframe[title="TerryDirector 导演时间线"]');
  await expect(reopened.locator("#missingCount")).toContainText("7 个待重新链接");
  await expect(reopened.locator("#refCount")).toHaveText("8");
  await expect.poll(() => reopened.locator(".timeline-canvas.overlay")
    .evaluate(() => (window as any).TerryDirectorDemo.getState().clips.length)).toBe(9);
});
