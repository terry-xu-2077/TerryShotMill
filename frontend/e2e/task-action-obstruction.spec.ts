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
    await page.getByRole('button', { name: '管理任务', exact: true }).click();
    const batch = page.getByRole('region', { name: '任务操作', exact: true });
    const bounds = (await batch.boundingBox())!;
    expect(Math.abs(bounds.x + bounds.width / 2 - width / 2)).toBeLessThan(1);
    const statusbar = (await page.locator('.project-workspace-statusbar').boundingBox())!;
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(statusbar.y - 8);
    await batch.getByRole('button', { name: '全选', exact: true }).click();
    await batch.getByRole('button', { name: '取消选择' }).click();
    await page.getByRole('button', { name: '完成管理' }).click();
  }
  await page.screenshot({ path: info.outputPath("actions-clear-of-tasks.png") });
});

 test("management controls and fixed inspector stay aligned; folders are centered", async ({ page }) => {
  const project = await createProject(page, "管理布局");
  await createTask(page, project.id, "第一条");
  await createTask(page, project.id, "第二条");
  await openProject(page, project.title);
  let inspectorWidth = 0;
  for (const width of [1366, 940, 780]) {
    await page.setViewportSize({ width, height: 850 });
    await page.locator('.task-list-row:not(.is-create)').first().click();
    const inspector = (await page.locator('.project-task-info').boundingBox())!;
    if (!inspectorWidth) inspectorWidth = inspector.width;
    expect(inspector.width).toBe(inspectorWidth);
    await expect(page.getByRole('checkbox', { name: /^选择任务/ })).toHaveCount(0);
    await page.getByRole('button', { name: '管理任务', exact: true }).click();
    const checks = page.getByRole('checkbox', { name: /^选择任务/ });
    await expect(checks).toHaveCount(2);
    await expect(checks.first()).not.toBeChecked();
    const item = page.locator('.task-collection-item').first();
    const box = (await item.locator('.task-selection-control').boundingBox())!;
    const row = (await item.locator('.task-item-content').boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(row.x + row.width);
    const bar = page.getByRole('region', { name: '任务操作', exact: true });
    await bar.getByRole('button', { name: '全选', exact: true }).click();
    await expect(checks.first()).toBeChecked();
    const left = (await bar.getByRole('group', { name: '生成操作' }).boundingBox())!;
    const right = (await bar.getByRole('group', { name: '选择操作' }).boundingBox())!;
    expect(right.x).toBeGreaterThan(left.x + left.width);
    await page.getByRole('button', { name: '完成管理' }).click();
  }
  await page.getByRole('button', { name: '返回项目首页' }).click();
  const grid = page.locator('.project-folder-grid');
  const geometry = await grid.evaluate(el => {
    const bounds = el.getBoundingClientRect();
    const cells = Array.from(el.children).map(child => child.getBoundingClientRect());
    return {left: Math.min(...cells.map(c => c.left)) - bounds.left, right: bounds.right - Math.max(...cells.map(c => c.right))};
  });
  expect(Math.abs(geometry.left - geometry.right)).toBeLessThan(2);
 });

test("top navigation keeps its natural width with long project titles", async ({ page }) => {
  const project = await createProject(page, "异星边境 · 电影第一、二场 · 720P · 长项目标题");
  await openProject(page, project.title);
  let expected: number[] = [];
  for (const width of [1600, 940, 780]) {
    await page.setViewportSize({ width, height: 850 });
    const widths = await page.locator('.workspace-navigation > button').evaluateAll(nodes => nodes.map(n => n.getBoundingClientRect().width));
    if (!expected.length) expected = widths;
    widths.forEach((value, index) => expect(Math.abs(value - expected[index])).toBeLessThan(1));
    const navigation = (await page.locator('.workspace-navigation').boundingBox())!;
    const title = (await page.locator('.workspace-project-title').boundingBox())!;
    const actions = (await page.locator('.workspace-top-actions').boundingBox())!;
    expect(navigation.x + navigation.width).toBeLessThanOrEqual(title.x);
    expect(title.x + title.width).toBeLessThanOrEqual(actions.x);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test("task heading remains visible while list and cards scroll", async ({ page }) => {
  const project = await createProject(page, "常驻任务工具栏");
  for (let i = 0; i < 18; i++) await createTask(page, project.id, `任务${i}`);
  await openProject(page, project.title);
  for (const mode of ['list', 'card']) {
    if (mode === 'card') await page.getByRole('button', { name: '切换为卡片视图' }).click();
    const heading = page.locator('.task-collection-heading');
    const before = (await heading.boundingBox())!;
    await page.locator('.project-task-area').evaluate(el => {
      for (const node of [el, ...el.querySelectorAll('*')]) {
        if (node.scrollHeight > node.clientHeight && getComputedStyle(node).overflowY === 'auto') node.scrollTop = 500;
      }
    });
    expect((await heading.boundingBox())!.y).toBe(before.y);
    await page.getByRole('button', { name: '管理任务', exact: true }).click();
    await expect(page.getByRole('button', { name: '完成管理' })).toBeVisible();
    await page.getByRole('button', { name: '完成管理' }).click();
  }
});
