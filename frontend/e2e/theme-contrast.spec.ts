import { expect, test, type Locator } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { textContrast } from "./contrast";
import { createProject, importImage, openProject } from "./helpers";

test("common actions, selected modes and supporting text remain readable in both themes", async ({ page }, testInfo) => {
  const project = await createProject(page, "主题对比度");
  const asset = await importImage(page, project.id, "参考场景");
  expect((await page.request.post(`/api/v1/projects/${project.id}/tasks`, { data: {
    title: "对比度检查", userPrompt: "角色走入基地", assetBindings: [{ assetId: asset.id, role: "reference", reference: "<Picture 1>" }],
  } })).ok()).toBeTruthy();
  await openProject(page, project.title);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.locator(".task-list-row:not(.is-create)").click();
  const measurements: object[] = [];
  const failures: string[] = [];
  for (const theme of ["亮色", "暗色"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    const sample = async (name: string, locator: Locator, minimum = 4.5) => {
      const color = await textContrast(locator, name.startsWith("项目") ? { selector: ".project-folder-front", pseudo: "::before" } : undefined);
      measurements.push({ theme, name, ...color });
      if (color.minimumRatio < minimum) failures.push(`${theme} / ${name}: ${color.minimumRatio.toFixed(2)}`);
    };
    await page.getByRole("button", { name: "返回项目首页", exact: true }).click();
    const folder = page.getByRole("button", { name: `打开项目 ${project.title}`, exact: true });
    await sample("项目名称", folder.locator("h2"));
    await sample("项目日期", folder.locator(".project-folder-date"));
    await sample("项目简介", folder.locator(".project-folder-description"));
    await sample("项目统计", folder.locator("footer span").first());
    await folder.screenshot({ path: testInfo.outputPath(`${theme}-folder.png`) });
    await folder.click();
    await page.locator(".task-list-row:not(.is-create)").click();
    await sample("编辑任务", page.getByRole("button", { name: "编辑任务", exact: true }));
    await sample("当前生成", page.getByRole("button", { name: "生成视频", exact: true }));
    await sample("任务状态", page.locator(".task-plain-status").last());
    await page.locator(".task-list-row:not(.is-create)").dblclick();
    const dialog = page.getByRole("dialog");
    const parameters = dialog.getByRole("button", { name: "生成参数", exact: true });
    if (await parameters.getAttribute("aria-expanded") !== "true") await parameters.click();
    for (const button of await dialog.getByRole("tab", { selected: true }).all()) await sample("选中标签", button);
    await sample("参数说明", dialog.locator(".simple-context-detail-slot p"));
    const save = dialog.getByRole("button", { name: "保存", exact: true });
    await page.mouse.move(0, 0);
    await sample("保存", save);
    await save.hover();
    await sample("保存悬停", save);
    await sample("取消", dialog.getByRole("button", { name: "取消", exact: true }));
    await dialog.getByRole("tab", { name: "文本", exact: true }).click();
    await dialog.getByRole("textbox", { name: "用户提示词", exact: true }).fill("@");
    const menu = page.getByRole("listbox", { name: "引用任务资产" });
    await expect(menu).toBeVisible();
    await sample("引用名称", menu.locator(".prompt-asset-menu-copy strong"));
    await sample("引用说明", menu.locator(".prompt-asset-menu-copy small"));
    await sample("引用操作提示", menu.locator("footer span").first());
    await sample("引用图标", menu.locator(".prompt-asset-menu-thumb"), 3);
    await page.screenshot({ path: testInfo.outputPath(`${theme}-menu.png`) });
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await sample("设置标签", page.locator(".application-settings-field > span").first());
    await sample("设置保存", page.getByRole("button", { name: "保存设置", exact: true }));
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  await testInfo.attach("theme-contrast", { body: JSON.stringify(measurements, null, 2), contentType: "application/json" });
  await writeFile(testInfo.outputPath("measurements.json"), JSON.stringify(measurements, null, 2), "utf8");
  expect(failures).toEqual([]);
});
