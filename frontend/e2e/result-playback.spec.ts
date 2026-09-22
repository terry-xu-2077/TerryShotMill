import { expect, test } from "@playwright/test";
import { createProject, createTask, openProject } from "./helpers";

test("result playback stays inside the dialog on desktop and mobile", async ({ page }) => {
  const project = await createProject(page, "结果播放");
  await createTask(page, project.id, "播放测试");
  await page.route(`**/projects/${project.id}/workspace`, async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    Object.assign(data.tasks[0], { status: "completed", resultCount: 1,
      primaryResult: { id: "result-1", videoUrl: "/playback-test.mp4" } });
    await route.fulfill({ json: data });
  });
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").click();
  await page.getByRole("button", { name: "播放任务 播放测试 的生成结果" }).click();
  const dialog = page.getByRole("dialog", { name: "播放结果 · 播放测试" });
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await expect(dialog.getByRole("button", { name: "关闭", exact: true })).toBeVisible();
    await expect.poll(() => dialog.evaluate((element) => {
      const content = element.querySelector(".sm-dialog-content")!;
      const video = element.querySelector("video")!.getBoundingClientRect();
      const frame = element.getBoundingClientRect();
      return content.scrollWidth <= content.clientWidth + 1 && video.right <= frame.right;
    })).toBe(true);
  }
});
