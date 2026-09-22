import { expect, test } from "@playwright/test";
import { createProject, createTask, importImage, openProject } from "./helpers";

test("slot picker uses asset categories alongside a compact search field", async ({ page }, info) => {
  const original = await (await page.request.get("/api/v1/application/settings")).json();
  try {
    await page.request.patch("/api/v1/application/settings", { data: { ...original, comfyui: { ...original.comfyui, defaultProfileId: "tags", workflowProfiles: [{ id: "tags", name: "标签测试", workflowFile: "tags.json", resolution: "", quality: "", enabled: true }] } } });
    await page.route("**/api/v1/comfyui/workflows", route => route.fulfill({ json: [{ id: "tags.json", name: "标签测试", fileName: "tags.json", relativePath: "tags.json", executable: true, hasShotmillBridge: true, inputs: [{ name: "image", type: "IMAGE", direction: "input", sourceNodeId: "1", targetNodeId: "2", targetPort: "image" }], outputs: [], warnings: [] }] }));
    const project = await createProject(page, "资产标签");
    await createTask(page, project.id);
    for (const [name, tag] of [["角色参考", "人物"], ["场景参考", "环境"]]) {
      const asset = await importImage(page, project.id, name);
      expect((await page.request.patch(`/api/v1/projects/${project.id}/assets/${asset.id}`, { data: { tags: [tag], category: tag === "人物" ? "character" : "scene" } })).ok()).toBeTruthy();
    }
    await openProject(page, project.title);
    await page.locator(".task-list-row:not(.is-create)").dblclick();
    await page.getByRole("button", { name: /图片 1/ }).click();
    const picker = page.getByRole("dialog", { name: "选择资产 · 图片 1" });
    await picker.evaluate(async el => { await Promise.all(el.getAnimations().map(animation => animation.finished)); });
    const initialBounds = await picker.boundingBox();
    const row = await picker.locator(".workflow-slot-filters").boundingBox();
    const search = await picker.locator(".workflow-slot-search").boundingBox();
    expect(search!.width / row!.width).toBeGreaterThan(0.27);
    expect(search!.width / row!.width).toBeLessThan(0.31);
    await expect(picker.getByRole("tab", { name: "场景", exact: true })).toBeVisible();
    await expect(picker.getByRole("tab", { name: "人物", exact: true })).toHaveCount(0);
    await picker.getByRole("tab", { name: "角色", exact: true }).click();
    await expect(picker.getByRole("button", { name: "填入 角色参考" })).toBeVisible();
    await expect(picker.getByRole("button", { name: "填入 场景参考" })).toHaveCount(0);
    await picker.getByPlaceholder("搜索项目资产").fill("不存在");
    await expect(picker.getByText("没有匹配的项目资产")).toBeVisible();
    expect(await picker.boundingBox()).toEqual(initialBounds);
    await picker.getByPlaceholder("搜索项目资产").fill("");
    await expect(picker.getByRole("button", { name: "填入 角色参考" })).toBeVisible();
    for (const category of ["全部", "场景", "道具", "参考", "角色"]) {
      await picker.getByRole("tab", { name: category, exact: true }).click();
      expect(await picker.boundingBox()).toEqual(initialBounds);
      await expect(picker.getByRole("button", { name: "取消", exact: true })).toBeInViewport();
    }
    await page.screenshot({ path: info.outputPath("asset-filter.png") });
  } finally { await page.request.patch("/api/v1/application/settings", { data: original }); }
});
