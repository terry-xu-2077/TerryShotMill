import { expect, test } from "@playwright/test";
import { createProject, openProject } from "./helpers";

test("theme persists across reloads and settings tabs preserve unsaved inference values", async ({ page }) => {
  const project = await createProject(page, "主题切换");
  await page.goto("/");
  await page.getByRole("button", { name: "暗色", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-tc-mode", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-tc-mode", "dark");
  await openProject(page, project.title);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("tab", { name: "API推理", exact: true }).click();
  await dialog.getByLabel("模型名称", { exact: true }).fill("unsaved-theme-test");
  await dialog.getByRole("tab", { name: "外观", exact: true }).click();
  await dialog.getByRole("button", { name: "亮色", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-tc-mode", "light");
  await dialog.getByRole("tab", { name: "AI 增强", exact: true }).click();
  await expect(dialog.getByLabel("模型名称", { exact: true })).toHaveValue("unsaved-theme-test");
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByRole("button", { name: "亮色", exact: true })).toHaveAttribute("aria-pressed", "true");
});

test("reduced motion suppresses the collection entrance animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const duration = await page.locator(".project-folder-grid").evaluate((element) => getComputedStyle(element).animationDuration);
  expect(parseFloat(duration)).toBeLessThanOrEqual(0.001);
});
