import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("task actions never cover another selectable task", async ({ page }, info) => {
  const project = await createProject(page, "操作栏避让");
  for (let i = 1; i <= 5; i++) await createTask(page, project.id, `任务${i}`);
  await openProject(page, project.title);
  for (const width of [1366, 780]) {
    await page.setViewportSize({ width, height: 850 });
    const rows = page.locator(".task-list-row:not(.is-create)");
    await page.getByRole("region", { name: "任务区域" }).evaluate(async element => {
      await Promise.all(element.getAnimations({ subtree: true }).map(animation => animation.finished));
    });
    const before = await rows.nth(1).boundingBox();
    await rows.first().click();
    const bar = page.getByRole("region", { name: "任务操作", exact: true });
    await expect(bar).toBeVisible();
    await expect(bar.getByRole('button')).toHaveCount(2);
    const edit = (await bar.getByRole('button', { name: '编辑任务' }).boundingBox())!;
    const generate = (await bar.getByRole('button', { name: '生成视频' }).boundingBox())!;
    expect(Math.abs(edit.width - generate.width)).toBeLessThan(1);
    const preview = (await page.locator('.project-task-info .task-preview').boundingBox())!;
    const heading = (await page.locator('.project-task-info > h2').boundingBox())!;
    const controls = (await bar.boundingBox())!;
    expect(controls.y).toBeGreaterThanOrEqual(preview.y + preview.height);
    expect(controls.y + controls.height).toBeLessThanOrEqual(heading.y);
    expect(await rows.nth(1).boundingBox()).toEqual(before);
    await expect.poll(async () => {
      const bounds = await bar.boundingBox();
      const targets = await rows.evaluateAll(elements => elements.map(el => {
        const r = el.getBoundingClientRect();
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
      }));
      return targets.slice(1).some(r => bounds && bounds.x < r.right && bounds.x + bounds.width > r.left && bounds.y < r.bottom && bounds.y + bounds.height > r.top);
    }).toBe(false);
    // A real pointer click at the next row's centre must select it, without detouring.
    const next = (await rows.nth(1).boundingBox())!;
    await page.mouse.click(next.x + next.width / 2, next.y + next.height / 2);
    await expect(rows.nth(1)).toHaveClass(/is-selected/);
    await page.getByRole('button', { name: '全选任务', exact: true }).click();
    const batch = page.getByRole('region', { name: '任务操作', exact: true });
    const bounds = (await batch.boundingBox())!;
    expect(Math.abs(bounds.x + bounds.width / 2 - width / 2)).toBeLessThan(1);
    expect(bounds.y + bounds.height).toBeGreaterThan(840);
    await batch.getByRole('button', { name: '取消选择' }).click();
  }
  await page.screenshot({ path: info.outputPath("actions-clear-of-tasks.png") });
});
