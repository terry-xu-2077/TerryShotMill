import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("queued and generating tasks remain distinct in both views and details", async ({ page }) => {
  const project = await createProject(page, "视频队列状态");
  await createTask(page, project.id, "等待项");
  await createTask(page, project.id, "正在生成项");
  await page.route(`**/projects/${project.id}/workspace`, async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.tasks.forEach((task: { title: string; status: string; videoGenerationStatus: string }) => {
      task.status = "running";
      task.videoGenerationStatus = task.title === "等待项" ? "queued" : "running";
    });
    await route.fulfill({ json: data });
  });
  await openProject(page, project.title);
  const area = page.getByRole("region", { name: "任务区域" });
  for (const view of ["卡片", "表格"]) {
    await expect(area.getByRole("button").filter({ hasText: "#1 等待项" })).toContainText("排队中");
    await expect(area.getByRole("button").filter({ hasText: "#2 正在生成项" })).toContainText("生成中");
    await expect(page.locator(".workspace-runtime-summary")).toContainText("正在生成项");
    await expect(page.locator(".workspace-runtime-summary")).toContainText("排队 1 项");
    await area.getByText("#1 等待项", { exact: true }).click();
    await expect(page.getByRole("complementary", { name: "任务信息" })).toContainText("排队中");
    await page.getByRole("button", { name: `切换为${view}视图` }).click();
  }
});
