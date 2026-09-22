import { expect, test } from "@playwright/test";
import { createProject, openProject } from "./helpers";

test("language presets preserve the selected prompt when settings reopen", async ({ page }) => {
  const original = await (await page.request.get("/api/v1/application/settings")).json();
  const project = await createProject(page, "系统提示词语言");
  try {
    await openProject(page, project.title);
    for (const name of ["MiniMax H3 · 中文输出", "MiniMax H3 · 英文输出"]) {
      await page.getByRole("button", { name: "设置", exact: true }).click();
      await page.getByRole("tab", { name: "AI 增强", exact: true }).click();
      const select = page.getByRole("combobox", { name: "系统提示词预设" });
      await select.click();
      await page.getByRole("option", { name, exact: true }).click();
      const preset = original.systemPromptPresets.find((item: { name: string }) => item.name === name);
      await expect(page.getByRole("textbox", { name: "系统提示词", exact: true })).toHaveValue(preset.prompt);
      await page.getByRole("button", { name: "保存设置", exact: true }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await page.getByRole("button", { name: "设置", exact: true }).click();
      await page.getByRole("tab", { name: "AI 增强", exact: true }).click();
      await expect(select).toContainText(name);
      await expect(page.getByRole("textbox", { name: "系统提示词", exact: true })).toHaveValue(preset.prompt);
      await page.keyboard.press("Escape");
    }
  } finally { await page.request.patch("/api/v1/application/settings", { data: original }); }
});
