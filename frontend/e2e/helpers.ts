import { expect, type Page } from "@playwright/test";

export async function createProject(page: Page, titlePrefix = "E2E 项目") {
  const title = `${titlePrefix} ${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  const response = await page.request.post("/api/v1/projects", {
    data: { title },
  });
  expect(response.ok()).toBeTruthy();
  return { id: (await response.json()).id as string, title };
}

export async function createTask(page: Page, projectId: string, title = "雨夜抵达仓库") {
  const response = await page.request.post(`/api/v1/projects/${projectId}/tasks`, {
    data: {
      title,
      summary: "角色抵达仓库入口",
      userIntent: "角色穿过雨夜码头，抵达仓库入口",
      userPrompt: "角色穿过雨夜码头，抵达仓库入口",
      promptSource: "user",
      durationSeconds: 6,
      generation: {
        resolution: "1080p",
        quality: "标准",
        mode: "全能参考",
        contextMode: "不承接",
      },
      assetBindings: [],
    },
  });
  expect(response.ok()).toBeTruthy();
  return await response.json() as { id: string };
}

export async function importImage(page: Page, projectId: string, name = "林澜主视觉") {
  const response = await page.request.post(`/api/v1/projects/${projectId}/assets`, {
    multipart: {
      file: {
        name: "linlan.png",
        mimeType: "image/png",
        buffer: Buffer.from("e2e-image-bytes"),
      },
      name,
      category: "character",
      tags: "[]",
    },
  });
  expect(response.ok()).toBeTruthy();
  return await response.json() as { id: string };
}

export async function openProject(page: Page, title: string) {
  await page.goto("/dev/ui");
  await expect(page.getByRole("main", { name: "项目首页" })).toBeVisible();
  await page.getByRole("button", { name: `打开项目 ${title}` }).click();
  await expect(page.getByRole("main", { name: "项目工作台" })).toBeVisible();
}

export async function useTextPrompt(page: Page, value: string) {
  const displayModes = page.getByRole("tablist", { name: "用户提示词显示模式" });
  await displayModes.getByRole("tab", { name: /文本/ }).click();
  const prompt = page.getByRole("textbox", { name: "用户提示词" });
  await prompt.fill(value);
  return prompt;
}

export async function selectAllTasks(page: Page) {
  const manage = page.getByRole("button", { name: "管理任务", exact: true });
  if (await manage.isVisible()) await manage.click();
  await page.getByRole("button", { name: "全选", exact: true }).click();
}
