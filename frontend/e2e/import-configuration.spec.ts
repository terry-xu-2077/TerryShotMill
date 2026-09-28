import { expect, test } from "@playwright/test";
import { createProject, createTask } from "./helpers";

for (const mode of ["light", "dark"] as const) {
  for (const width of [1366, 390]) {
    test(`import configuration restores generation ${mode} ${width}`, async ({ page }, testInfo) => {
      const settings = await (await page.request.get("/api/v1/application/settings")).json();
      try {
        const configured = await page.request.patch("/api/v1/application/settings", { data: {
          ...settings, comfyui: { ...settings.comfyui, defaultProfileId: "local", workflowProfiles: [
            { id: "local", name: "本机测试工作流", workflowFile: "fixture.json", enabled: true },
          ] },
        } });
        expect(configured.ok()).toBeTruthy();
        const original = await createProject(page, "迁移配置");
        await createTask(page, original.id, "待确认任务");
        const exported = await page.request.get(`/api/v1/projects/${original.id}/export`);
        expect(exported.ok()).toBeTruthy();
        const imported = await page.request.post("/api/v1/projects/import", { multipart: {
          file: { name: "project.zip", mimeType: "application/zip", buffer: await exported.body() },
        } });
        expect(imported.status()).toBe(201);
        const id = (await imported.json()).projectId;
        expect((await page.request.post(`/api/v1/projects/${original.id}/lifecycle`, {
          data: { action: "archive" },
        })).ok()).toBeTruthy();
        const pending = await (await page.request.get(`/api/v1/projects/${id}/import-configuration`)).json();
        const taskId = pending[0].taskId;
        const blocked = await page.request.post(`/api/v1/projects/${id}/tasks/${taskId}/generation`, { data: {} });
        expect(blocked.status()).toBe(409);
        expect((await blocked.json()).error.code).toBe("GENERATION_CONFIGURATION_REQUIRED");
        await page.setViewportSize({ width, height: 844 });
        await page.goto("/dev/ui");
        await page.getByRole("button", { name: mode === "light" ? "亮色" : "暗色", exact: true }).click();
        await page.getByRole("button", { name: "项目管理", exact: true }).click();
        const manager = page.getByRole("dialog", { name: "项目管理", exact: true });
        await manager.locator(".project-lifecycle-row").filter({ hasText: original.title })
          .getByRole("button", { name: "确认生成配置" }).click();
        const dialog = page.getByRole("dialog", { name: "确认生成配置", exact: true });
        await expect(dialog.getByRole("button", { name: "确认配置", exact: true })).toBeDisabled();
        await dialog.getByRole("combobox").click();
        await page.getByRole("option", { name: "本机测试工作流", exact: true }).click();
        const box = await dialog.boundingBox();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(width);
        expect(box!.y + box!.height).toBeLessThanOrEqual(844);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
        await page.screenshot({ path: testInfo.outputPath(`configuration-${mode}-${width}.png`) });
        await dialog.getByRole("button", { name: "确认配置", exact: true }).click();
        await expect(dialog.getByRole("status")).toHaveText("没有待确认的任务。");
        const submitted = await page.request.post(`/api/v1/projects/${id}/tasks/${taskId}/generation`, { data: {} });
        expect(submitted.status()).toBe(202);
        await expect.poll(async () => {
          const workspace = await (await page.request.get(`/api/v1/projects/${id}/workspace`)).json();
          return workspace.tasks[0].resultCount;
        }).toBeGreaterThan(0);
      } finally {
        await page.request.patch("/api/v1/application/settings", { data: settings });
      }
    });
  }
}
