import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("task entrances are staggered, bounded, and do not replay on selection or theme changes", async ({ page }) => {
  const project = await createProject(page, "入场节奏");
  for (let index = 0; index < 8; index++) await createTask(page, project.id, `任务 ${index + 1}`);
  await openProject(page, project.title);
  const rows = page.locator(".task-list-row:not(.is-create)");
  const timings = await rows.evaluateAll((elements) => elements.map((element) => {
    const style = getComputedStyle(element);
    return { name: style.animationName, delay: parseFloat(style.animationDelay), duration: parseFloat(style.animationDuration) };
  }));
  expect(timings.every((timing) => timing.name === "collection-enter")).toBe(true);
  expect(timings[0].delay).toBeLessThan(timings[1].delay);
  expect(Math.max(...timings.map((timing) => timing.delay))).toBeLessThanOrEqual(0.21);
  expect(Math.max(...timings.map((timing) => timing.delay + timing.duration))).toBeLessThanOrEqual(0.6);
  await page.locator(".task-list-view").evaluate(async (element) => {
    await Promise.all(element.getAnimations({ subtree: true }).map((animation) => animation.finished));
    element.setAttribute("data-animation-restarts", "0");
    element.addEventListener("animationstart", () => {
      element.setAttribute("data-animation-restarts", String(Number(element.getAttribute("data-animation-restarts")) + 1));
    });
  });
  await rows.nth(2).click();
  await page.getByRole("button", { name: "暗色", exact: true }).click();
  await expect(page.locator(".task-list-view")).toHaveAttribute("data-animation-restarts", "0");
  await page.getByRole("button", { name: "切换为卡片视图", exact: true }).click();
  await expect(page.locator(".task-card-item.is-selected")).toContainText("任务 3");
  await expect(page.locator(".task-card-item").first()).toHaveCSS("animation-name", "collection-enter");
  await page.emulateMedia({ reducedMotion: "reduce" });
  const reduced = await page.locator(".task-card-item").last().evaluate((element) => {
    const style = getComputedStyle(element);
    return { delay: parseFloat(style.animationDelay), duration: parseFloat(style.animationDuration) };
  });
  expect(reduced.delay).toBe(0);
  expect(reduced.duration).toBeLessThanOrEqual(0.001);
});

test("expanding parameters animates content without moving the editor frame or save controls", async ({ page }) => {
  const project = await createProject(page, "参数过渡");
  await createTask(page, project.id);
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").dblclick();
  const dialog = page.getByRole("dialog");
  await dialog.evaluate(async (element) => {
    await Promise.all(element.getAnimations({ subtree: true }).map((animation) => animation.finished));
  });
  const frame = await dialog.boundingBox();
  const actions = await page.locator(".simple-task-editor-actions").boundingBox();
  await page.getByRole("button", { name: "生成参数", exact: true }).click();
  await expect(page.locator(".task-parameter-content")).toHaveCSS("transition-property", "grid-template-rows, opacity");
  await page.locator(".task-parameter-content").evaluate(async (element) => {
    await Promise.all(element.getAnimations().map((animation) => animation.finished));
  });
  const blocks = page.locator(".simple-task-config > section");
  await expect(blocks).toHaveCount(3);
  for (const block of await blocks.all()) {
    await expect(block).toHaveCSS("border-radius", "16px");
    await expect(block).toHaveCSS("border-top-width", "1px");
  }
  expect(await dialog.boundingBox()).toEqual(frame);
  expect(await page.locator(".simple-task-editor-actions").boundingBox()).toEqual(actions);
  const parameterArea = await page.locator(".simple-task-config").boundingBox();
  expect(parameterArea!.height).toBeLessThan(145);
  const workflow = await page.getByRole("combobox", { name: "生成工作流" }).boundingBox();
  const duration = await page.locator(".simple-slider-field").boundingBox();
  expect(workflow!.x + workflow!.width).toBeLessThan(duration!.x);
  expect(Math.abs(workflow!.y + workflow!.height / 2 - duration!.y - duration!.height / 2)).toBeLessThan(2);
  for (const label of ["生成模式", "上下文承接方式"]) {
    const group = page.getByRole("tablist", { name: label });
    await expect(group).toHaveClass(/tc-segmented/);
    await expect(group.getByRole("tab").first()).toHaveCSS("border-top-left-radius", "999px");
    await expect(group.getByRole("tab").last()).toHaveCSS("border-top-right-radius", "999px");
  }
  await page.getByRole("button", { name: "生成参数", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "任务配置" })).toHaveCount(0);
  await expect(page.locator(".task-parameter-content")).toHaveAttribute("inert", "");
  await expect.poll(async () => (await page.locator(".task-parameter-content").boundingBox())?.height).toBe(0);
});

test("capsule actions and the single animated view icon stay consistent in both themes", async ({ page }) => {
  const project = await createProject(page, "按钮和图标");
  await createTask(page, project.id);
  await openProject(page, project.title);
  for (const theme of ["亮色", "暗色"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    for (const name of ["返回项目首页", "项目配置", "生成当前任务", "队列生成"]) {
      await expect(page.getByRole("button", { name, exact: true })).toHaveCSS("border-radius", "999px");
    }
    const toggle = page.locator(".task-view-control button");
    await expect(toggle).toHaveCount(1);
    await expect(toggle).toHaveText("");
    await expect(toggle).toHaveCSS("width", "32px");
    const icon = page.locator(".task-view-grid-icon");
    await expect(icon).toHaveCSS("transition-property", "opacity, transform");
    await page.getByRole("button", { name: "切换为卡片视图" }).click();
    await expect(icon).toHaveCSS("opacity", "1");
    await expect(page.locator(".task-view-list-icon")).toHaveCSS("opacity", "0");
    await page.getByRole("button", { name: "切换为表格视图" }).click();
  }
});
