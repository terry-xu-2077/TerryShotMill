import { expect, test, type Page } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

async function openTimeline(page: Page) {
  await page.locator(".sm-dialog").evaluate(async element => {
    await Promise.all(element.getAnimations({ subtree: true }).map(animation => animation.finished));
  });
  const parameters = page.getByRole("complementary", { name: "任务配置" });
  const frame = await parameters.boundingBox();
  await page.getByRole("button", { name: "调整承接区间", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "承接时间轴", exact: true })).toBeVisible();
  await expect(page.getByRole("slider", { name: "承接片段", exact: true })).toBeFocused();
  expect(await parameters.boundingBox()).toEqual(frame);
  expect(frame!.height).toBeLessThan(170);
}

test("a new task uses the previous result's actual duration before its first save", async ({ page }) => {
  const project = await createProject(page, "新任务承接成片");
  const source = await createTask(page, project.id, "计划六秒实际两秒");
  const generation = await page.request.post(`/api/v1/projects/${project.id}/tasks/${source.id}/generation`, { data: {} });
  const job = await generation.json();
  await expect.poll(async () => (await (await page.request.get(`/api/v1/jobs/${job.id}`)).json()).status).toBe("completed");
  await openProject(page, project.title);
  await page.getByRole("button", { name: "新建任务卡", exact: true }).click();
  await page.getByRole("button", { name: "生成参数", exact: true }).click();
  await page.getByRole("tab", { name: "片段承接", exact: true }).click();
  await openTimeline(page);
  await expect(page.getByRole("slider", { name: "承接终点" })).toHaveAttribute("aria-valuemax", "2");
  await expect(page.locator(".simple-context-range-control")).toContainText("1s – 2s · 1s");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const workspace = await (await page.request.get(`/api/v1/projects/${project.id}/workspace`)).json();
  expect(workspace.tasks).toHaveLength(2);
  const editor = await (await page.request.get(`/api/v1/projects/${project.id}/tasks/${workspace.tasks[1].id}/editor`)).json();
  expect(editor.generation.contextStartSeconds).toBe(1);
  expect(editor.generation.contextEndSeconds).toBe(2);
});

test("timeline clip moves as a whole, clamps without changing duration and trims by its edges", async ({ page }) => {
  const project = await createProject(page, "时间轴片段");
  await createTask(page, project.id, "六秒来源");
  const response = await page.request.post(`/api/v1/projects/${project.id}/tasks`, {
    data: { title: "片段块", userPrompt: "继续上一镜头", promptSource: "user",
      generation: { contextMode: "片段承接", contextStartSeconds: 1, contextEndSeconds: 3 } },
  });
  expect(response.ok()).toBeTruthy();
  const task = await response.json();
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").last().dblclick();
  await page.getByRole("button", { name: "生成参数", exact: true }).click();
  await openTimeline(page);
  const clip = page.getByRole("slider", { name: "承接片段", exact: true });
  await expect(clip).toBeVisible();
  await page.locator(".sm-dialog").evaluate(async element => {
    await Promise.all(element.getAnimations({ subtree: true }).map(animation => animation.finished));
  });
  const track = page.locator(".simple-context-range-control .tc-range-slider-track");
  const box = (await track.boundingBox())!;
  const atTime = (time: number) => box.x + box.width * time / 6;
  const dragClip = async (delta: number) => {
    const clipBox = (await clip.boundingBox())!;
    const x = clipBox.x + clipBox.width / 2;
    const y = clipBox.y + clipBox.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + box.width * delta / 6, y, { steps: 16 });
    await page.mouse.up();
  };
  await dragClip(2);
  await expect(clip).toHaveAttribute("aria-valuetext", "3s – 5s · 2s");
  await dragClip(5);
  await expect(clip).toHaveAttribute("aria-valuetext", "4s – 6s · 2s");
  await dragClip(-8);
  await expect(clip).toHaveAttribute("aria-valuetext", "0s – 2s · 2s");
  await clip.focus();
  await page.keyboard.press("End");
  await expect(clip).toHaveAttribute("aria-valuetext", "4s – 6s · 2s");
  await page.keyboard.press("Home");
  await page.keyboard.press("ArrowRight");
  await expect(clip).toHaveAttribute("aria-valuetext", "0.1s – 2.1s · 2s");
  const start = page.getByRole("slider", { name: "承接起点", exact: true });
  const startBox = (await start.boundingBox())!;
  await page.mouse.move(startBox.x + startBox.width / 2, startBox.y + startBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(atTime(0.5), startBox.y + startBox.height / 2, { steps: 10 });
  await page.mouse.up();
  await expect(clip).toHaveAttribute("aria-valuetext", "0.5s – 2.1s · 1.6s");
  await page.screenshot({ path: "test-results/context-timeline-clip.png" });
  await page.getByRole("dialog", { name: "承接时间轴", exact: true }).getByRole("button", { name: "完成", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "承接时间轴", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "调整承接区间", exact: true })).toContainText("0.5s – 2.1s · 1.6s");
  await openTimeline(page);
  await page.locator(".simple-prompt-body").click({ position: { x: 20, y: 20 } });
  await expect(page.getByRole("dialog", { name: "承接时间轴", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "调整承接区间", exact: true })).toContainText("0.5s – 2.1s · 1.6s");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const editor = await (await page.request.get(`/api/v1/projects/${project.id}/tasks/${task.id}/editor`)).json();
  expect(editor.generation.contextStartSeconds).toBe(0.5);
  expect(editor.generation.contextEndSeconds).toBe(2.1);
  for (const theme of ["亮色", "暗色"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    for (const size of [{ width: 1366, height: 768 }, { width: 960, height: 540 }]) {
      await page.setViewportSize(size);
      await page.locator(".task-list-row:not(.is-create)").last().dblclick();
      await page.getByRole("button", { name: "生成参数", exact: true }).click();
      await openTimeline(page);
      await expect(clip).toHaveAttribute("aria-valuetext", "0.5s – 2.1s · 1.6s");
      await page.locator(".sm-dialog").evaluate(async element => {
        await Promise.all(element.getAnimations({ subtree: true }).map(animation => animation.finished));
      });
      const save = (await page.getByRole("button", { name: "保存", exact: true }).boundingBox())!;
      expect(save.y + save.height).toBeLessThanOrEqual(size.height);
      const currentClip = (await clip.boundingBox())!;
      expect(currentClip.y).toBeGreaterThanOrEqual(0);
      expect(currentClip.y + currentClip.height).toBeLessThanOrEqual(save.y);
      const readout = (await page.locator(".simple-context-range-control output").boundingBox())!;
      const popup = (await page.getByRole("dialog", { name: "承接时间轴", exact: true }).boundingBox())!;
      expect(readout.y + readout.height).toBeLessThanOrEqual(popup.y + popup.height);
      expect(popup.y).toBeGreaterThanOrEqual(0);
      expect(popup.y + popup.height).toBeLessThanOrEqual(size.height);
      await page.screenshot({ path: `test-results/timeline-${theme}-${size.width}.png` });
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog", { name: "承接时间轴", exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "调整承接区间", exact: true })).toBeFocused();
      await expect(page.locator(".sm-dialog")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toHaveCount(0);
    }
  }
});

test("continuation timeline uses the generated video's duration instead of the plan", async ({ page }) => {
  const project = await createProject(page, "实际成片区间");
  const source = await createTask(page, project.id, "计划六秒实际两秒");
  const generation = await page.request.post(`/api/v1/projects/${project.id}/tasks/${source.id}/generation`, { data: {} });
  expect(generation.ok()).toBeTruthy();
  const job = await generation.json();
  await expect.poll(async () => (await (await page.request.get(`/api/v1/jobs/${job.id}`)).json()).status).toBe("completed");
  const target = await page.request.post(`/api/v1/projects/${project.id}/tasks`, {
    data: { title: "末尾一秒", userPrompt: "继续上一镜头", generation: { contextMode: "片段承接" } },
  });
  expect(target.ok()).toBeTruthy();
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").last().dblclick();
  await page.getByRole("button", { name: "生成参数", exact: true }).click();
  await openTimeline(page);
  await expect(page.getByRole("slider", { name: "承接终点" })).toHaveAttribute("aria-valuemax", "2");
  await expect(page.locator(".simple-context-range-control")).toContainText("1s – 2s · 1s");
});

test("continuation handles share a timeline and drag independently before save and reopen", async ({ page }) => {
  const project = await createProject(page, "上下文区间");
  await createTask(page, project.id, "上一任务");
  const response = await page.request.post(`/api/v1/projects/${project.id}/tasks`, {
    data: {
      title: "区间承接", userPrompt: "继续上一镜头", promptSource: "user", durationSeconds: 6,
      generation: { contextMode: "片段承接", contextStartSeconds: 1, contextEndSeconds: 5 },
      assetBindings: [],
    },
  });
  expect(response.ok()).toBeTruthy();
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").last().dblclick();
  await page.getByRole("button", { name: "生成参数", exact: true }).click();
  await openTimeline(page);
  const start = page.getByRole("slider", { name: "承接起点" });
  const end = page.getByRole("slider", { name: "承接终点" });
  const track = page.locator(".simple-context-range-control");
  await expect(start).toBeVisible();
  await page.locator(".sm-dialog").evaluate(async (element) => {
    await Promise.all(element.getAnimations({ subtree: true }).map((animation) => animation.finished));
  });
  // Drag from the selected interval's actual end, not a DOM-only change event.
  const selection = page.locator(".simple-context-range-selection, .tc-range-slider-selection");
  const box = await selection.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x + box!.width, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2, { steps: 20 });
  await page.mouse.up();
  await expect(track).toContainText("1s – 3s");
  await start.focus();
  await page.keyboard.press("ArrowRight");
  await expect(start).toHaveAttribute("aria-valuenow", "1.1");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").last().dblclick();
  await page.getByRole("button", { name: "生成参数", exact: true }).click();
  await openTimeline(page);
  await expect(track).toContainText("1.1s – 3s · 1.9s");
  await expect(end).toHaveAttribute("aria-valuenow", "3");
  // As on the first open, finish the parameter expansion before measuring drag coordinates.
  await page.locator(".sm-dialog").evaluate(async (element) => {
    await Promise.all(element.getAnimations({ subtree: true }).map((animation) => animation.finished));
  });

  const startBox = await start.boundingBox();
  const endBox = await end.boundingBox();
  const selectedBox = await selection.boundingBox();
  expect(Math.abs(startBox!.x + startBox!.width / 2 - selectedBox!.x)).toBeLessThan(1);
  expect(Math.abs(endBox!.x + endBox!.width / 2 - selectedBox!.x - selectedBox!.width)).toBeLessThan(1);

  // Bring the handles close enough that their hit areas overlap, then drag the start.
  await start.focus();
  await page.keyboard.press("End");
  await expect(start).toHaveAttribute("aria-valuenow", "2.9");
  const closeBox = await start.boundingBox();
  expect(await start.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const hit = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
    return hit?.closest(".tc-range-slider-input") === element.closest(".tc-range-slider-input");
  })).toBe(true);
  await page.mouse.move(closeBox!.x + closeBox!.width / 2, closeBox!.y + closeBox!.height / 2);
  await page.mouse.down();
  await page.mouse.move(startBox!.x + startBox!.width / 2, closeBox!.y + closeBox!.height / 2, { steps: 20 });
  await expect(start).toHaveAttribute("aria-valuenow", "1.1");
  await expect(end).toHaveAttribute("aria-valuenow", "3");
  await page.mouse.up();
  await page.screenshot({ path: "test-results/context-range-fixed.png" });
});
