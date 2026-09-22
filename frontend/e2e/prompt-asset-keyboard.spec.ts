import { expect, test } from "@playwright/test";
import { createProject, importImage, openProject } from "./helpers";

test("asset references support keyboard selection and Escape dismisses only the menu in both editor modes", async ({ page }, testInfo) => {
  const project = await createProject(page, "引用键盘验收");
  const first = await importImage(page, project.id, "人物参考");
  const second = await importImage(page, project.id, "场景参考");
  const response = await page.request.post(`/api/v1/projects/${project.id}/tasks`, { data: {
    title: "引用键盘", userPrompt: "镜头参考 ",
    assetBindings: [first, second].map((asset, index) => ({ assetId: asset.id, role: "reference", reference: `<Picture ${index + 1}>` })),
  } });
  expect(response.ok()).toBeTruthy();
  await openProject(page, project.title);
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const theme of ["亮色", "暗色"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    await page.setViewportSize({ width: 960, height: 540 });
    await page.locator(".task-list-row:not(.is-create)").dblclick();
    const dialog = page.getByRole("dialog", { name: /引用键盘/ });
    for (const mode of ["文本", "可视化"]) {
      await dialog.getByRole("tab", { name: mode, exact: true }).click();
      const prompt = dialog.getByRole("textbox", { name: mode === "文本" ? "用户提示词" : "用户提示词可视化", exact: true });
      const menu = page.getByRole("listbox", { name: "引用任务资产" });
      await prompt.fill("镜头参考 @");
      await expect(menu.getByRole("option")).toHaveCount(2);
      await expect(prompt).toBeFocused();
      await page.keyboard.press("ArrowDown");
      await expect(menu.getByRole("option").nth(1)).toHaveAttribute("aria-selected", "true");
      const activeId = await prompt.getAttribute("aria-activedescendant");
      expect(activeId).toBe(await menu.getByRole("option").nth(1).getAttribute("id"));
      const bounds = await menu.boundingBox();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.y).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(960);
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(540);
      await page.screenshot({ path: testInfo.outputPath(`${theme}-${mode}-references.png`) });
      await page.keyboard.press("Enter");
      await expect(menu).toHaveCount(0);
      await expect(prompt).toBeFocused();
      if (mode === "文本") await expect(prompt).toHaveValue(/<Picture 2>/);
      else await expect(prompt.locator('[data-raw="<Picture 2>"]')).toHaveText("场景参考");
      await prompt.fill("镜头参考 @");
      await page.keyboard.press("ArrowUp");
      await expect(menu.getByRole("option").nth(1)).toHaveAttribute("aria-selected", "true");
      await page.keyboard.press("Tab");
      await expect(menu).toHaveCount(0);
      await expect(prompt).toBeFocused();
      await prompt.fill("镜头参考 @");
      await expect(menu).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(menu).toHaveCount(0);
      await expect(dialog).toBeVisible();
      await expect(prompt).toBeFocused();
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".task-list-row:not(.is-create)")).toBeFocused();
  }
});
