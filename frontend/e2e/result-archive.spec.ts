import { expect, test } from "@playwright/test";
import { createProject, createTask } from "./helpers";

for (const mode of ["light", "dark"] as const) {
for (const width of [1366, 390]) {
test(`archive deletion preserves imported media · ${mode} · ${width}`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 844 });
  await page.addInitScript(theme => localStorage.setItem("shotmill.color-theme", theme), mode);
  const source = await createProject(page, "已删除来源");
  const target = await createProject(page, "导入目标");
  const task = await createTask(page, source.id, "保留全部版本");
  for (let version = 0; version < 2; version++) {
    const submitted = await page.request.post(`/api/v1/projects/${source.id}/tasks/${task.id}/generation`, { data: {} });
    expect(submitted.ok()).toBeTruthy();
    const job = await submitted.json();
    await expect.poll(async () => (await (await page.request.get(`/api/v1/jobs/${job.id}`)).json()).status).toBe("completed");
  }
  expect((await page.request.post(`/api/v1/projects/${source.id}/lifecycle`, { data: { action: "trash" } })).ok()).toBeTruthy();
  const purge = await page.request.post(`/api/v1/projects/${source.id}/permanent-delete`, {
    data: { confirmed: true, archiveResults: true },
  });
  expect(purge.ok()).toBeTruthy();
  expect((await purge.json()).archivedResultCount).toBe(2);
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: "生成结果归档", exact: true }).click();
  const archive = page.getByRole("dialog", { name: "生成结果归档", exact: true });
  const group = archive.getByRole("region", { name: `原项目 · ${source.title}` });
  await expect(group.getByRole("button", { name: "查看结果" })).toHaveCount(2);
  await group.getByRole("button", { name: "查看结果" }).first().click();
  const preview = page.getByRole("dialog", { name: "归档结果 · 保留全部版本" });
  const download = preview.getByRole("link", { name: /下载原文件/ });
  const response = await page.request.get((await download.getAttribute("href"))!);
  expect(response.ok()).toBeTruthy();
  expect(response.headers()["content-disposition"]).toContain("attachment");
  expect((await response.body()).length).toBeGreaterThan(0);
  await preview.evaluate(async element => {
    await Promise.all(element.getAnimations().map(animation => animation.finished));
  });
  const bounds = await preview.boundingBox();
  await preview.getByRole("button", { name: "生成信息", exact: true }).click();
  expect(await preview.boundingBox()).toEqual(bounds);
  await expect(preview.getByText("角色穿过雨夜码头，抵达仓库入口", { exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("archived-result.png") });
  await page.keyboard.press("Escape");
  await group.getByRole("button", { name: "导入项目" }).first().click();
  const importer = page.getByRole("dialog", { name: "导入归档结果" });
  await importer.getByRole("button", { name: target.title, exact: true }).click();
  await importer.getByRole("button", { name: "导入", exact: true }).click();
  await expect(importer.getByRole("status")).toHaveText("已导入，可在目标项目的项目资产中找到。");
  const assets = await page.request.get(`/api/v1/projects/${target.id}/assets`);
  const imported = (await assets.json()).items;
  expect(imported).toHaveLength(1);
  expect(imported[0].provenance.projectId).toBe(source.id);
  await importer.getByRole("button", { name: "完成", exact: true }).click();
  await group.getByRole("button", { name: "删除归档" }).first().click();
  const confirmation = page.getByRole("dialog", { name: "永久删除归档结果", exact: true });
  await expect(confirmation.getByRole("button", { name: "取消" })).toBeFocused();
  await confirmation.evaluate(async element => {
    await Promise.all(element.closest("dialog")!.getAnimations({ subtree: true })
      .map(animation => animation.finished));
  });
  const confirmBounds = await confirmation.boundingBox();
  expect(confirmBounds).not.toBeNull();
  expect(confirmBounds!.x).toBeGreaterThanOrEqual(0);
  expect(confirmBounds!.x + confirmBounds!.width).toBeLessThanOrEqual(width);
  expect(confirmBounds!.y + confirmBounds!.height).toBeLessThanOrEqual(844);
  await page.screenshot({ path: info.outputPath("archive-delete-confirm.png") });
  await confirmation.getByRole("button", { name: "取消" }).click();
  await expect(group.getByRole("button", { name: "删除归档" })).toHaveCount(2);
  await group.getByRole("button", { name: "删除归档" }).first().click();
  const deleted = page.waitForResponse(response => response.request().method() === "DELETE"
    && response.url().includes("/result-archive/"));
  await confirmation.getByRole("button", { name: "永久删除", exact: true }).click();
  expect((await deleted).status()).toBe(204);
  await expect(group.getByRole("button", { name: "删除归档" })).toHaveCount(1);
  const remaining = await (await page.request.get(`/api/v1/result-archive?sourceProjectId=${source.id}`)).json();
  expect(remaining).toHaveLength(1);
  const assetFile = await page.request.get(`/media/${target.id}/${imported[0].projectRelativePath}`);
  expect(assetFile.ok()).toBeTruthy();
  expect((await assetFile.body()).length).toBeGreaterThan(0);
});
}
}
