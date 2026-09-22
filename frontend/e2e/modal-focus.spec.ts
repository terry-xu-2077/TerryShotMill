import { expect, test } from "@playwright/test";
import { createProject, createTask, importImage, openProject } from "./helpers";

test("modal moves focus inside, contains Tab, blocks background focus and restores its trigger", async ({ page }) => {
  await page.goto("/dev/ui");
  const trigger = page.getByRole("button", { name: /新建项目/ });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "新建项目" });
  await expect.poll(() => dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  await expect(dialog.getByRole("textbox").first()).toBeFocused();
  for (let index = 0; index < 12; index++) {
    await page.keyboard.press("Tab");
    await expect.poll(() => dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  }
  for (let index = 0; index < 12; index++) {
    await page.keyboard.press("Shift+Tab");
    await expect.poll(() => dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  }
  await trigger.evaluate((element: HTMLElement) => element.focus());
  await expect.poll(() => dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("nested image preview restores parent focus and Escape closes one layer", async ({ page }) => {
  const project = await createProject(page, "焦点嵌套");
  await importImage(page, project.id, "焦点图片");
  await openProject(page, project.title);
  const trigger = page.getByRole("button", { name: "项目配置", exact: true });
  await trigger.click();
  const config = page.getByRole("dialog", { name: "项目配置", exact: true });
  await config.getByRole("button", { name: "资产管理" }).click();
  const image = config.getByRole("button", { name: "放大 焦点图片" });
  await image.click();
  const preview = page.getByRole("dialog", { name: "焦点图片", exact: true });
  await expect.poll(() => preview.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(preview).toHaveCount(0);
  await expect(config).toBeVisible();
  await expect(image).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(config).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("Escape dismisses a workflow menu before its containing editor", async ({ page }) => {
  const original = await (await page.request.get("/api/v1/application/settings")).json();
  await page.request.patch("/api/v1/application/settings", { data: {
    ...original, comfyui: { ...original.comfyui, defaultProfileId: "focus-standard", workflowProfiles: [
      { id: "focus-standard", name: "键盘标准", resolution: "720p", quality: "标准", workflowFile: "standard.json", enabled: true },
      { id: "focus-detail", name: "键盘精细", resolution: "1080p", quality: "高质量", workflowFile: "detail.json", enabled: true },
    ] },
  } });
  try {
    const project = await createProject(page, "菜单键盘");
    await createTask(page, project.id);
    await openProject(page, project.title);
    await page.locator(".task-list-row:not(.is-create)").dblclick();
    const editor = page.getByRole("dialog");
    await editor.getByRole("button", { name: "生成参数", exact: true }).click();
    const select = editor.getByRole("combobox", { name: "生成工作流" });
    await select.click();
    await expect(page.getByRole("listbox")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("listbox")).toHaveCount(0);
    await expect(editor).toBeVisible();
    await expect(select).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(page.getByRole("option", { name: "键盘标准" })).toBeFocused();
    await page.keyboard.press("End");
    await expect(page.getByRole("option", { name: "键盘精细" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(select).toContainText("键盘精细");
    await expect(select).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(editor).toHaveCount(0);
  } finally {
    await page.request.patch("/api/v1/application/settings", { data: original });
  }
});

test("video playback keeps keyboard focus and restores the clicked poster", async ({ page }) => {
  const project = await createProject(page, "播放器焦点");
  const task = await createTask(page, project.id, "播放焦点任务");
  const response = await page.request.post(`/api/v1/projects/${project.id}/tasks/${task.id}/generation`, { data: {} });
  expect(response.ok()).toBeTruthy();
  const job = await response.json();
  await expect.poll(async () => (await (await page.request.get(`/api/v1/jobs/${job.id}`)).json()).status).toBe("completed");
  await openProject(page, project.title);
  const poster = page.getByRole("button", { name: "播放视频 · 播放焦点任务", exact: true });
  await poster.click();
  const player = page.getByRole("dialog");
  await expect.poll(() => player.locator("video.is-active").evaluate((video: HTMLVideoElement) => !video.paused && video.currentTime > 0)).toBe(true);
  for (const direction of ["Tab", "Shift+Tab"]) {
    for (let index = 0; index < 15; index++) {
      await page.keyboard.press(direction);
      await expect.poll(() => player.evaluate(element => element.contains(document.activeElement))).toBe(true);
    }
  }
  await page.keyboard.press("Escape");
  await expect(player).toHaveCount(0);
  await expect(poster).toBeFocused();
});

test("compact modal layouts keep their actions visible in both themes with reduced motion", async ({ page }) => {
  const project = await createProject(page, "紧凑弹窗");
  await createTask(page, project.id);
  await openProject(page, project.title);
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const theme of ["亮色", "暗色"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    // 960 × 540 CSS pixels is the layout viewport of a 1920 × 1080 display at 200% zoom.
    for (const size of [{ width: 1366, height: 768 }, { width: 960, height: 540 }]) {
      await page.setViewportSize(size);
      await page.getByRole("button", { name: "项目配置", exact: true }).click();
      const dialog = page.getByRole("dialog", { name: "项目配置", exact: true });
      const save = dialog.getByRole("button", { name: "保存", exact: true });
      const box = await save.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.y + box!.height).toBeLessThanOrEqual(size.height);
      expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `test-results/modal-${theme}-${size.width}.png` });
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(page.getByRole("button", { name: "项目配置", exact: true })).toBeFocused();
    }
  }
});

test.describe("compact layout at two device pixels per CSS pixel", () => {
  test.use({ deviceScaleFactor: 2, viewport: { width: 960, height: 540 } });

  test("long prompts scroll inside the editor while actions and the dialog frame remain visible", async ({ page }, testInfo) => {
    const project = await createProject(page, "高密度长内容");
    const title = "异星边境第一场：" + "远征队穿过漫长的沙暴抵达基地入口".repeat(5);
    const prompt = Array.from({ length: 60 }, (_, i) => `[Shot ${i + 1}] <d>[Chinese] 继续前进，保持队形。</d>\n`).join("");
    const response = await page.request.post(`/api/v1/projects/${project.id}/tasks`, { data: { title, userPrompt: prompt } });
    expect(response.ok()).toBeTruthy();
    await openProject(page, project.title);
    expect(await page.evaluate(() => devicePixelRatio)).toBe(2);
    await page.emulateMedia({ reducedMotion: "reduce" });
    for (const theme of ["亮色", "暗色"]) {
      await page.getByRole("button", { name: theme, exact: true }).click();
      await page.locator(".task-list-row:not(.is-create)").dblclick();
      const dialog = page.getByRole("dialog");
      await dialog.evaluate(async element => {
        const backdrop = element.closest('.sm-dialog-backdrop') ?? element;
        await Promise.all(backdrop.getAnimations({ subtree: true }).map(animation => animation.finished));
      });
      const frame = await dialog.boundingBox();
      const parameters = dialog.getByRole("button", { name: "生成参数", exact: true });
      if (await parameters.getAttribute("aria-expanded") !== "true") await parameters.click();
      for (const mode of ["文本", "可视化"]) {
        await dialog.getByRole("tab", { name: mode, exact: true }).click();
        const editor = dialog.getByRole("textbox", { name: mode === "文本" ? "用户提示词" : "用户提示词可视化", exact: true });
        await editor.click();
        await page.keyboard.press("ControlOrMeta+End");
        expect(await editor.evaluate(element => element.scrollHeight > element.clientHeight && element.scrollTop > 0)).toBe(true);
        expect(await dialog.boundingBox()).toEqual(frame);
        await page.screenshot({ path: testInfo.outputPath(`${theme}-${mode}-density-2.png`) });
        const overflow = await dialog.evaluate(element => ({ horizontal: element.scrollWidth - element.clientWidth, vertical: element.scrollHeight - element.clientHeight }));
        expect(overflow.horizontal).toBeLessThanOrEqual(1);
        expect(overflow.vertical).toBeLessThanOrEqual(1);
        const save = dialog.getByRole("button", { name: "保存", exact: true });
        const bounds = await save.boundingBox();
        expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(540);
        expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(960);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      }
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(page.locator(".task-list-row:not(.is-create)")).toBeFocused();
      await page.getByRole("button", { name: "设置", exact: true }).click();
      const settings = page.getByRole("dialog", { name: "设置", exact: true });
      for (const tab of ["AI 增强", "生成工作流", "外观"]) {
        await settings.getByRole("tab", { name: tab, exact: true }).click();
        const bounds = await settings.getByRole("button", { name: "保存设置", exact: true }).boundingBox();
        expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(540);
        expect(await settings.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
      }
      await page.keyboard.press("Escape");
      await expect(settings).toHaveCount(0);
    }
  });
});
