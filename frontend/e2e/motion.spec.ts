import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("folder cover keeps a short eased travel even when reduced motion is reported", async ({ page }, info) => {
  const project = await createProject(page, "文件夹弹出");
  const task = await createTask(page, project.id);
  const submitted = await page.request.post(`/api/v1/projects/${project.id}/tasks/${task.id}/generation`, { data: {} });
  expect(submitted.ok()).toBeTruthy();
  const job = await submitted.json();
  await expect.poll(async () => (await (await page.request.get(`/api/v1/jobs/${job.id}`)).json()).status).toBe("completed");
  const emptyProject = await createProject(page, "空文件夹配色对照");
  await page.goto("/dev/ui");
  const folder = page.getByRole("button", { name: `打开项目 ${project.title}`, exact: true });
  const emptyFolder = page.getByRole("button", { name: `打开项目 ${emptyProject.title}`, exact: true });
  await folder.evaluate(async element => { await Promise.all(element.getAnimations({ subtree: true }).map(a => a.finished)); });
  const cover = folder.locator(".project-folder-cover");
  await expect(folder).toHaveClass(/has-cover/);
  await expect(folder.locator(".project-folder-sheet")).toHaveCount(3);
  const papers = folder.locator(".project-folder-paper, .project-folder-paper-middle");
  for (const theme of ["亮色", "暗色"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    await expect(folder.locator(".project-folder-paper")).toHaveCSS("background-color", "rgb(209, 216, 223)");
    await expect(folder.locator(".project-folder-paper-middle")).toHaveCSS("background-color", "rgb(225, 229, 233)");
    const palette = (element: Element) => {
      const css = getComputedStyle(element);
      return ["--folder-color", "--folder-front", "--folder-ink"].map(name => css.getPropertyValue(name));
    };
    expect(await folder.evaluate(palette)).toEqual(await emptyFolder.evaluate(palette));
  }
  const cardBox = await folder.boundingBox();
  // The square reserves space for the raised cover; that space is not a hit target.
  await page.mouse.move(cardBox!.x + cardBox!.width / 2, cardBox!.y + 12);
  expect(await folder.evaluate(element => element.matches(":hover"))).toBe(false);
  await expect(cover).toHaveCSS("transform", "none");
  await page.mouse.click(cardBox!.x + cardBox!.width / 2, cardBox!.y + 12);
  await expect(page.getByRole("main", { name: "项目首页" })).toBeVisible();
  const rest = await cover.boundingBox();
  const style = await cover.evaluate(element => {
    const css = getComputedStyle(element);
    return { property: css.transitionProperty, easing: css.transitionTimingFunction, duration: css.transitionDuration, border: css.borderTopWidth };
  });
  expect(style.property).toContain("transform");
  expect(style.easing).toContain("cubic-bezier(0.2, 1.5, 0.32, 1)");
  expect(parseFloat(style.duration)).toBeCloseTo(0.3, 2);
  expect(style.border).toBe("1px");
  await folder.hover();
  await cover.evaluate(async element => { await Promise.all(element.getAnimations().map(a => a.finished)); });
  for (const paper of await papers.all()) await expect(paper).toHaveCSS("transform", "none");
  const raised = await cover.boundingBox();
  const travel = rest!.y - raised!.y;
  expect(travel / rest!.height).toBeCloseTo(0.2904, 3);
  expect(travel / cardBox!.height).toBeGreaterThan(0.10);
  expect(travel / cardBox!.height).toBeLessThan(0.18);
  expect((rest!.y - cardBox!.y) / cardBox!.height).toBeGreaterThan(0.37);
  expect(await folder.boundingBox()).toEqual(cardBox);
  await page.screenshot({ path: info.outputPath("folder-raised.png") });
  await page.mouse.move(0, 0);
  await cover.evaluate(async element => { await Promise.all(element.getAnimations().map(a => a.finished)); });
  expect(Math.abs((await cover.boundingBox())!.y - rest!.y)).toBeLessThan(1);
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(await cover.evaluate(el => parseFloat(getComputedStyle(el).transitionDuration))).toBeGreaterThanOrEqual(0.25);
  await folder.hover();
  const animation = await cover.evaluate(element => {
    const motion = element.getAnimations().find(a => a instanceof CSSTransition && a.transitionProperty === "transform");
    return motion ? { duration: motion.effect!.getTiming().duration, state: motion.playState, easing: motion.effect!.getTiming().easing } : null;
  });
  expect(animation).not.toBeNull();
  expect(Number(animation!.duration)).toBeGreaterThanOrEqual(250);
  expect(animation!.easing).toBe("cubic-bezier(0.2, 1.5, 0.32, 1)");
  await cover.evaluate(async element => { await Promise.all(element.getAnimations().map(a => a.finished)); });
  expect(Math.abs((await cover.boundingBox())!.y - raised!.y)).toBeLessThan(1);
  await page.mouse.move(0, 0);
  await folder.focus();
  await expect(folder).toBeFocused();
  await folder.press("Enter");
  await expect(page.getByRole("main", { name: "项目工作台" })).toBeVisible();
});

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
  expect(reduced.delay).toBeLessThanOrEqual(0.21);
  expect(reduced.duration).toBeGreaterThan(0.001);
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
  await page.locator('.task-list-row:not(.is-create)').first().click();
  for (const theme of ["亮色", "暗色"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    for (const name of ["返回项目首页", "项目配置", "编辑任务", "生成视频"]) {
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
