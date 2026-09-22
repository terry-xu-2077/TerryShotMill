import { expect, test } from "@playwright/test";
import { createProject, openProject } from "./helpers";

const richPrompt = `summary: 荒星的清晨，探险者停下脚步。
[Shot 1] [00:02] <Subject 1> 望向远处的基地。The camera pushes in
(S1) <d>[zh] 再撑一段，我们就快到了。</d>
<scenetrans> [Shot 2] <Picture 1> 风吹过岩石。fully_preserved`;

test("remembers visual/text per task and per prompt without saving cancelled edits or changing source/review", async ({ page }) => {
  const project = await createProject(page, "显示模式记忆");
  const root = `/api/v1/projects/${project.id}/tasks`;
  const first = await (await page.request.post(root, { data: {
    title: "镜头一", userPrompt: richPrompt, aiEnhancedPrompt: richPrompt, promptSource: "ai",
  } })).json();
  const second = await (await page.request.post(root, { data: {
    title: "镜头二", userPrompt: richPrompt, aiEnhancedPrompt: richPrompt, promptSource: "user",
  } })).json();
  expect((await page.request.post(`${root}/${first.id}/prompt-review`, { data: { action: "approve" } })).ok()).toBeTruthy();
  const before = await (await page.request.get(`${root}/${first.id}/editor`)).json();
  const reviewBefore = await (await page.request.get(`/api/v1/projects/${project.id}/prompt-review-state`)).json();
  const versions = page.getByRole("tablist", { name: "提示词版本" });
  const modes = () => page.getByRole("tablist", { name: /提示词显示模式/ });
  const changeMode = async (label: string) => {
    const saved = page.waitForResponse(response => response.url().endsWith("/editor-preference") && response.request().method() === "PATCH");
    await modes().getByRole("tab", { name: label, exact: true }).click();
    expect((await saved).ok()).toBeTruthy();
  };
  await openProject(page, project.title);
  await page.locator(".task-list-row").filter({ hasText: "镜头一" }).dblclick();
  await expect(versions.getByRole("tab", { name: /AI 增强/ })).toHaveAttribute("aria-selected", "true");
  await versions.getByRole("tab", { name: "用户", exact: true }).click();
  await changeMode("文本");
  await page.getByRole("textbox", { name: "用户提示词", exact: true }).fill("不应自动保存的草稿");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.locator(".task-list-row").filter({ hasText: "镜头二" }).dblclick();
  await expect(modes().getByRole("tab", { name: "可视化", exact: true })).toHaveAttribute("aria-selected", "true");
  await versions.getByRole("tab", { name: /AI 增强/ }).click();
  await changeMode("文本");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await openProject(page, project.title); // full reload, no component/local state available
  for (const [title, source, userMode, aiMode] of [
    ["镜头一", "AI 增强", "文本", "可视化"], ["镜头二", "用户", "可视化", "文本"],
  ]) {
    await page.locator(".task-list-row").filter({ hasText: title }).dblclick();
    await expect(versions.getByRole("tab", { name: source, exact: true })).toHaveAttribute("aria-selected", "true");
    await versions.getByRole("tab", { name: "用户", exact: true }).click();
    await expect(modes().getByRole("tab", { name: userMode, exact: true })).toHaveAttribute("aria-selected", "true");
    await versions.getByRole("tab", { name: /AI 增强/ }).click();
    await expect(modes().getByRole("tab", { name: aiMode, exact: true })).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  const after = await (await page.request.get(`${root}/${first.id}/editor`)).json();
  expect(after).toEqual({ ...before, editorPreference: { userViewMode: "text", aiViewMode: "visual" } });
  expect(await (await page.request.get(`/api/v1/projects/${project.id}/prompt-review-state`)).json()).toEqual(reviewBefore);
  expect((await (await page.request.get(`${root}/${second.id}/editor`)).json()).editorPreference).toEqual({ userViewMode: "visual", aiViewMode: "text" });
});

test("failed display preference can be retried without losing the draft", async ({ page }) => {
  const project = await createProject(page, "显示偏好重试");
  const root = `/api/v1/projects/${project.id}/tasks`;
  const task = await (await page.request.post(root, { data: { title: "重试镜头", userPrompt: richPrompt } })).json();
  await openProject(page, project.title);
  await page.locator(".task-list-row:not(.is-create)").dblclick();
  await page.route("**/editor-preference", route => route.fulfill({ status: 503, body: "{}" }), { times: 1 });
  await page.getByRole("tablist", { name: "用户提示词显示模式" }).getByRole("tab", { name: "文本", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("显示偏好未记住");
  const prompt = page.getByRole("textbox", { name: "用户提示词", exact: true });
  await prompt.fill("继续编辑的草稿");
  const saved = page.waitForResponse(response => response.url().endsWith("/editor-preference") && response.ok());
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await saved;
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(prompt).toHaveValue("继续编辑的草稿");
  const editor = await (await page.request.get(`${root}/${task.id}/editor`)).json();
  expect(editor.editorPreference.userViewMode).toBe("text");
  expect(editor.userPrompt).toBe(richPrompt);
});

test("visual prompt tokens and dialogue stay legible and distinct in both themes", async ({ page }, testInfo) => {
  const project = await createProject(page, "提示词配色");
  const response = await page.request.post(`/api/v1/projects/${project.id}/tasks`, {
    data: { title: "配色场景", userPrompt: richPrompt, aiEnhancedPrompt: richPrompt, promptSource: "user" },
  });
  expect(response.ok()).toBeTruthy();
  await openProject(page, project.title);
  for (const theme of ["亮色", "暗色"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    await page.locator(".task-list-row:not(.is-create)").dblclick();
    for (const source of ["用户", "AI 增强"]) {
      await page.getByRole("tablist", { name: "提示词版本" }).getByRole("tab", { name: source, exact: true }).click();
      const editor = page.getByRole("textbox", { name: `${source}提示词可视化` });
      await expect(editor.locator(".is-dialogue")).toHaveCount(1);
      const colors = await editor.evaluate(element => {
        const context = document.createElement("canvas").getContext("2d")!;
        const rgba = (value: string) => {
          context.clearRect(0, 0, 1, 1);
          context.fillStyle = value;
          context.fillRect(0, 0, 1, 1);
          return [...context.getImageData(0, 0, 1, 1).data].map((channel, index) => index === 3 ? channel / 255 : channel);
        };
        const over = (fg: number[], bg: number[]) => fg.slice(0, 3).map((value, i) => value * fg[3] + bg[i] * (1 - fg[3])).concat(1);
        const background = (node: Element | null): number[] => {
          if (!node) return [255, 255, 255, 1];
          const color = rgba(getComputedStyle(node).backgroundColor);
          return color[3] === 1 ? color : over(color, background(node.parentElement));
        };
        const luminance = (color: number[]) => color.slice(0, 3).map(value => {
          const srgb = value / 255;
          return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
        }).reduce((sum, value, i) => sum + value * [0.2126, 0.7152, 0.0722][i], 0);
        const ratio = (a: number[], b: number[]) => {
          const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
          return (values[0] + 0.05) / (values[1] + 0.05);
        };
        return [element, ...element.querySelectorAll(".h3-visual-chip, .h3-dialogue-text, .h3-dialogue-language")].map(node => {
          const style = getComputedStyle(node);
          const bg = background(node);
          return { kind: node.className, contrast: ratio(over(rgba(style.color), bg), bg),
            border: ratio(over(rgba(style.borderLeftColor), background(element)), background(element)) };
        });
      });
      for (const sample of colors) expect(sample.contrast, `${theme}: ${sample.kind}`).toBeGreaterThanOrEqual(4.5);
      expect(colors.find(sample => sample.kind.includes("is-dialogue"))!.border).toBeGreaterThanOrEqual(3);
      await testInfo.attach(`${theme}-${source}-contrast`, { body: JSON.stringify(colors, null, 2), contentType: "application/json" });
      await editor.screenshot({ path: `test-results/prompt-colors-${theme}-${source}.png` });
    }
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
});

test("dark visual dialogue remains readable while editing and selecting at desktop and compact sizes", async ({ page }) => {
  const project = await createProject(page, "暗色可视化检查");
  expect((await page.request.post(`/api/v1/projects/${project.id}/tasks`, {
    data: { title: "暗色对白", userPrompt: richPrompt, aiEnhancedPrompt: richPrompt },
  })).ok()).toBeTruthy();
  await openProject(page, project.title);
  await page.getByRole("button", { name: "暗色", exact: true }).click();
  for (const width of [1366, 960]) {
    await page.setViewportSize({ width, height: width === 960 ? 540 : 768 });
    await page.locator(".task-list-row:not(.is-create)").dblclick();
    for (const source of ["用户", "AI 增强"]) {
      await page.getByRole("tablist", { name: "提示词版本" }).getByRole("tab", { name: source, exact: true }).click();
      const editor = page.getByRole("textbox", { name: `${source}提示词可视化` });
      const dialogue = editor.locator(".h3-dialogue-text");
      await dialogue.fill("再撑一段，我们就快到了。");
      await dialogue.press("End");
      await dialogue.press("Shift+Home");
      expect(await page.evaluate(() => getSelection()?.toString())).toBe("再撑一段，我们就快到了。");
      await page.getByRole("dialog").screenshot({ path: `test-results/dark-dialogue-selected-${source}-${width}.png` });
      await dialogue.press("ArrowRight");
      await dialogue.press("!");
      await expect(dialogue).toContainText("到了。!");
      const language = editor.getByRole("combobox", { name: "对白语言" });
      await language.selectOption("Chinese");
      await language.focus();
      await expect(language).toBeFocused();
      await expect(language).toHaveCSS("outline-style", "solid");
      await page.getByRole("dialog").screenshot({ path: `test-results/dark-dialogue-editing-${source}-${width}.png` });
      const bounds = await editor.locator(".is-dialogue").boundingBox();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
      await page.getByRole("button", { name: "保存", exact: true }).focus();
      await editor.getByRole("combobox", { name: "对白语言" }).selectOption("English");
      const modes = page.getByRole("tablist", { name: /提示词显示模式/ });
      await modes.getByRole("tab", { name: "文本", exact: true }).click();
      await expect(page.getByRole("textbox", { name: `${source}提示词`, exact: true })).toHaveValue(/<d>\[English\].*到了。!<\/d>/);
      await modes.getByRole("tab", { name: "可视化", exact: true }).click();
    }
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
});
