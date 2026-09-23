import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("long workflow names stay in their slot and the library menu escapes the parameter panel", async ({ page }, info) => {
  const original = await (await page.request.get("/api/v1/application/settings")).json();
  const names = ["均衡档", "异星边境 · 上下文对照 · 超长工作流预设名称用于测试完整菜单与秒数布局", "精细档", "快速档"];
  try {
    expect((await page.request.patch("/api/v1/application/settings", { data: {
      ...original, comfyui: { ...original.comfyui, defaultProfileId: "layout-0", workflowProfiles: names.map((name, index) => ({
        id: `layout-${index}`, name, resolution: "720p", quality: "标准", workflowFile: "standard.json", enabled: true,
      })) },
    } })).ok()).toBeTruthy();
    const project = await createProject(page, "参数布局");
    await createTask(page, project.id);
    await openProject(page, project.title);
    await page.emulateMedia({ reducedMotion: "reduce" });
    for (const width of [1366, 960]) for (const theme of ["亮色", "暗色"]) {
      await page.setViewportSize({ width, height: width === 960 ? 540 : 768 });
      await page.getByRole("button", { name: theme, exact: true }).click();
      await page.locator(".task-list-row:not(.is-create)").dblclick();
      const toggle = page.getByRole("button", { name: "生成参数", exact: true });
      if (await toggle.getAttribute("aria-expanded") !== "true") await toggle.click();
      const select = page.getByRole("combobox", { name: "生成工作流" });
      await select.click();
      const menu = page.getByRole("listbox", { name: "生成工作流" });
      await expect(menu).toBeVisible();
      expect((await menu.boundingBox())!.height).toBeGreaterThan(120);
      await expect(page.getByRole("option", { name: names[3], exact: true })).toBeInViewport();
      await page.getByRole("option", { name: names[1], exact: true }).click();
      const bounds = await select.boundingBox();
      const seconds = await page.locator(".simple-slider-field").boundingBox();
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(seconds!.x);
      await expect(page.getByRole("slider", { name: "总秒数", exact: true })).toHaveClass(/sm-slider-range/);
      const numeric = await page.getByRole("spinbutton", { name: "总秒数数值" }).boundingBox();
      expect(numeric!.x + numeric!.width).toBeLessThanOrEqual(seconds!.x + seconds!.width + 1);
      await select.click();
      await page.screenshot({ path: info.outputPath(`${width}-${theme}-menu.png`) });
      await page.keyboard.press("Escape");
      await expect(select).toBeFocused();
      await page.keyboard.press("Escape");
    }
  } finally { await page.request.patch("/api/v1/application/settings", { data: original }); }
});

test("long folder titles and descriptions never stretch cards or the page", async ({ page }, info) => {
  const project = await createProject(page, "超长项目名称".repeat(15));
  expect((await page.request.patch(`/api/v1/projects/${project.id}`, { data: { description: "这是需要末端省略的项目简介".repeat(30) } })).ok()).toBeTruthy();
  await createProject(page, "空项目");
  await page.goto("/dev/ui");
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of [1366, 960, 390]) for (const theme of ["亮色", "暗色"]) {
    await page.setViewportSize({ width, height: 844 });
    await page.getByRole("button", { name: theme, exact: true }).click();
    const folder = page.getByRole("button", { name: `打开项目 ${project.title}`, exact: true });
    const geometry = await folder.evaluate(el => {
      const front = el.querySelector(".project-folder-front")!;
      return { card: el.getBoundingClientRect().width, front: front.getBoundingClientRect().width,
        overflow: document.querySelector(".project-home-collection")!.scrollWidth > innerWidth,
        titleOverflow: getComputedStyle(el.querySelector("h2")!).textOverflow,
        descriptionOverflow: getComputedStyle(el.querySelector(".project-folder-description")!).textOverflow };
    });
    expect(geometry.front).toBeLessThanOrEqual(geometry.card);
    const panelTransform = await folder.locator(".project-folder-front").evaluate(el => getComputedStyle(el, "::before").transform);
    expect(panelTransform).toContain("matrix3d");
    // Negative X rotation brings the upper edge forward: wider top, narrower bottom.
    expect(await page.evaluate(transform => new DOMMatrixReadOnly(transform).m23, panelTransform)).toBeLessThan(0);
    expect(geometry.overflow).toBe(false);
    expect(geometry.titleOverflow).toBe("ellipsis");
    expect(geometry.descriptionOverflow).toBe("ellipsis");
    await expect(folder).toHaveClass(/is-empty/);
    await expect(page.locator(".project-folder-grid > :first-child")).toHaveText("新建项目");
    await expect(page.locator(".project-folder-grid")).toHaveCSS("row-gap", "8px");
    await expect(page.locator(".project-folder-grid")).toHaveCSS("column-gap", "40px");
    const card = await folder.boundingBox();
    expect(card!.width / card!.height).toBeCloseTo(1, 1);
    expect(card!.width).toBeLessThanOrEqual(288);
    const folders = await page.locator(".project-folder-card:not(.project-create-card)").evaluateAll(elements => elements.map(el => {
      const { x, y, width } = el.getBoundingClientRect();
      return { x, y, width };
    }));
    for (const other of folders) {
      if (Math.abs(other.y - card!.y) < 1 && other.x < card!.x) expect(card!.x - other.x - other.width).toBeGreaterThanOrEqual(39);
    }
    const cover = folder.locator(".project-folder-cover");
    const rest = await cover.boundingBox();
    await expect(folder.locator(".project-folder-sheet")).toHaveCount(1);
    await expect(cover).toHaveCSS("background-color", "rgb(255, 255, 255)");
    await expect(cover.locator("svg")).toHaveCount(0);
    await folder.hover();
    await expect(cover).toHaveCSS("transform", "none");
    const hoveredCard = await folder.boundingBox();
    const hoveredCover = await cover.boundingBox();
    expect(hoveredCover!.y - hoveredCard!.y).toBeCloseTo(rest!.y - card!.y, 0);
    await folder.focus();
    await expect(cover).toHaveCSS("transform", "none");
    await page.mouse.move(0, 0);
    await page.screenshot({ path: info.outputPath(`${width}-${theme}-folders.png`) });
  }
});


test("new task opens visually and parameter controls share a center line", async ({ page }, info) => {
  const project = await createProject(page, "参数对齐");
  await createTask(page, project.id);
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").dblclick();
  await page.getByRole("tablist", { name: "用户提示词显示模式" }).getByRole("tab", { name: /文本/ }).click();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "新建任务卡", exact: true }).click();
  await expect(page.getByRole("tablist", { name: "用户提示词显示模式" }).getByRole("tab", { name: /可视化/ })).toHaveAttribute("aria-selected", "true");
  const toggle = page.getByRole("button", { name: "生成参数", exact: true });
  if (await toggle.getAttribute("aria-expanded") !== "true") await toggle.click();
  await page.locator(".task-parameter-content").evaluate(async el => { await Promise.all(el.getAnimations().map(animation => animation.finished)); });
  for (const width of [1366, 960]) {
    await page.setViewportSize({ width, height: 768 });
    const controls = [page.getByRole("combobox", { name: "生成工作流" }), page.locator(".simple-slider-field"), page.getByRole("tablist", { name: "生成模式", exact: true }), page.getByRole("tablist", { name: "上下文承接方式", exact: true })];
    await expect.poll(async () => {
      const boxes = await Promise.all(controls.map(control => control.boundingBox()));
      const centers = boxes.map(box => box!.y + box!.height / 2);
      return Math.max(...centers) - Math.min(...centers);
    }).toBeLessThan(2);
    const note = page.locator(".workflow-duration-note");
    const contextNote = page.locator(".simple-context-note");
    await expect(note).toHaveCSS("font-size", "12px");
    await expect(contextNote).toHaveCSS("font-size", "12px");
    await expect(note).toBeInViewport();
    await expect(contextNote).toBeInViewport();
    const a = await note.boundingBox();
    const b = await contextNote.boundingBox();
    expect(Math.abs(a!.y + a!.height - b!.y - b!.height)).toBeLessThan(2);
    await page.screenshot({ path: info.outputPath(`parameters-${width}.png`) });
  }
});

test("previous summary option shares the enhancement action row above asset slots", async ({ page }, info) => {
  const project = await createProject(page, "增强操作布局");
  await createTask(page, project.id);
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").dblclick();
  await page.getByRole("tablist", { name: "提示词版本" }).getByRole("tab", { name: "AI 增强", exact: true }).click();
  for (const width of [1366, 960]) {
    await page.setViewportSize({ width, height: 768 });
    const option = page.locator(".single-prompt-context-option");
    const enhance = page.getByRole("button", { name: "增强", exact: true });
    await expect(option).toBeVisible();
    await expect(enhance).toBeVisible();
    const a = await option.boundingBox();
    const b = await enhance.boundingBox();
    const assets = await page.locator(".workflow-input-slots").boundingBox();
    expect(Math.abs(a!.y + a!.height / 2 - b!.y - b!.height / 2)).toBeLessThan(2);
    expect(a!.x + a!.width).toBeLessThan(b!.x);
    expect(a!.y + a!.height).toBeLessThan(assets!.y);
    await expect(page.getByText(/可视化模式会将 H3 标签/)).toHaveCount(0);
    await page.screenshot({ path: info.outputPath(`enhance-row-${width}.png`) });
  }
});
