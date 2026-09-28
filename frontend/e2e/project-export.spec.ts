import { expect, test } from "@playwright/test";
import { createProject, createTask } from "./helpers";

test("native ZIP download can be imported again through the home dialog", async ({ page }) => {
  const original = await createProject(page, "导出验收");
  await createTask(page, original.id, "保留的任务");
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: "项目管理", exact: true }).click();
  const manager = page.getByRole("dialog", { name: "项目管理", exact: true });
  const row = manager.locator(".project-lifecycle-row").filter({ hasText: original.title });
  await row.getByRole("button", { name: "导出", exact: true }).click();
  const exporter = page.getByRole("dialog", { name: "导出项目", exact: true });
  await exporter.getByRole("button", { name: "打包项目" }).click();
  const link = exporter.getByRole("link", { name: "下载 ZIP" });
  await expect(link).toBeVisible();
  const downloadEvent = page.waitForEvent("download");
  await link.click();
  const download = await downloadEvent;
  expect(await download.failure()).toBeNull();
  expect(download.suggestedFilename()).toBe("shotmill-project.zip");
  const path = await download.path();
  expect(path).not.toBeNull();
  await exporter.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(exporter).toBeHidden();
  await manager.getByRole("button", { name: "关闭对话框" }).click();
  await expect(manager).toBeHidden();
  await page.getByRole("button", { name: "导入项目", exact: true }).click();
  const importer = page.getByRole("dialog", { name: "导入项目", exact: true });
  await importer.getByLabel("项目 ZIP 包").setInputFiles(path!);
  const importedEvent = page.waitForResponse(r => r.url().endsWith("/projects/import") && r.request().method() === "POST");
  await importer.getByRole("button", { name: "导入", exact: true }).click();
  const imported = await importedEvent;
  expect(imported.status()).toBe(201);
  const id = (await imported.json()).projectId;
  expect(id).not.toBe(original.id);
  const workspace = await page.request.get(`/api/v1/projects/${id}/workspace`);
  expect((await workspace.json()).tasks[0].title).toBe("保留的任务");
  await expect(importer.getByRole("status")).toHaveText("项目已导入");
});

test("export preparation error stays in the dialog and supports retry", async ({ page }) => {
  const project = await createProject(page, "导出失败验收");
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: "项目管理", exact: true }).click();
  const manager = page.getByRole("dialog", { name: "项目管理", exact: true });
  await manager.locator(".project-lifecycle-row").filter({ hasText: project.title })
    .getByRole("button", { name: "导出", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "导出项目", exact: true });
  await page.route(`**/projects/${project.id}/exports`, route => route.fulfill({
    status: 500, contentType: "application/json", body: JSON.stringify({ error: {
      code: "PROJECT_EXPORT_STORAGE_ERROR", message: "项目包写入失败，请检查磁盘空间和文件访问权限。",
    } }),
  }), { times: 1 });
  await dialog.getByRole("button", { name: "打包项目" }).click();
  await expect(dialog.getByRole("alert")).toContainText("检查磁盘空间");
  await dialog.getByRole("button", { name: "打包项目" }).click();
  await expect(dialog.getByRole("link", { name: "下载 ZIP" })).toBeVisible();
});
