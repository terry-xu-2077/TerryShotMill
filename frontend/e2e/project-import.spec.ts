import { expect, test } from "@playwright/test";
import { createProject, createTask } from "./helpers";

for (const mode of ["light", "dark"] as const) {
  for (const width of [1366, 390]) {
    test(`project ZIP import ${mode} ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 844 });
      const original = await createProject(page, "迁移验收");
      await createTask(page, original.id, "迁移任务");
      const exported = await page.request.get(`/api/v1/projects/${original.id}/export`);
      expect(exported.ok()).toBeTruthy();
      await page.goto("/dev/ui");
      await page.getByRole("button", { name: mode === "light" ? "亮色" : "暗色", exact: true }).click();
      await page.getByRole("button", { name: "导入项目", exact: true }).click();
      const dialog = page.getByRole("dialog", { name: "导入项目", exact: true });
      await dialog.getByLabel("项目 ZIP 包").setInputFiles({
        name: "项目迁移验收.zip", mimeType: "application/zip", buffer: await exported.body(),
      });
      const response = page.waitForResponse(r => r.url().endsWith("/projects/import") && r.request().method() === "POST");
      await dialog.getByRole("button", { name: "导入", exact: true }).click();
      const imported = await response;
      expect(imported.status()).toBe(201);
      const importedId = (await imported.json()).projectId;
      expect(importedId).not.toBe(original.id);
      await expect(dialog.getByRole("status")).toHaveText("项目已导入");
      const box = await dialog.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      expect(box!.y + box!.height).toBeLessThanOrEqual(844);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      const screenshot = testInfo.outputPath(`import-${mode}-${width}.png`);
      await page.screenshot({ path: screenshot });
      await testInfo.attach(`import-${mode}-${width}`, { path: screenshot, contentType: "image/png" });
      await dialog.getByRole("button", { name: "关闭", exact: true }).click();
      await expect(dialog).toBeHidden();
      await expect(page.getByRole("button", { name: `打开项目 ${original.title}`, exact: true })).toHaveCount(2);
      const workspace = await page.request.get(`/api/v1/projects/${importedId}/workspace`);
      expect(workspace.ok()).toBeTruthy();
      expect((await workspace.json()).tasks[0].title).toBe("迁移任务");
    });
  }
}

test("damaged ZIP keeps the import dialog open with a useful error", async ({ page }) => {
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: "导入项目", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "导入项目", exact: true });
  await dialog.getByLabel("项目 ZIP 包").setInputFiles({
    name: "损坏.zip", mimeType: "application/zip", buffer: Buffer.from("not a zip"),
  });
  await dialog.getByRole("button", { name: "导入", exact: true }).click();
  await expect(dialog.getByRole("alert")).toHaveText("项目包损坏或格式不受支持。");
  await expect(dialog.getByRole("button", { name: "导入", exact: true })).toBeEnabled();
});
