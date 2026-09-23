import { expect, test } from "@playwright/test";
import { createProject, openProject } from "./helpers";

test("user prompt history restores only on save and survives reload", async ({ page }) => {
  const project = await createProject(page, "用户提示词历史");
  const root = `/api/v1/projects/${project.id}/tasks`;
  const task = await (await page.request.post(root, { data: {title: '历史任务', userPrompt: '第一版描述', saveUserPromptVersion: true} })).json();
  const url = `${root}/${task.id}`;
  const editor = await (await page.request.get(`${url}/editor`)).json();
  expect((await page.request.patch(url, { data: {...editor, userPrompt: '第二版描述', saveUserPromptVersion: true} })).ok()).toBeTruthy();
  await openProject(page, project.title);
  const open = async () => page.locator('.task-list-row:not(.is-create)').first().dblclick();
  await open();
  const history = page.getByRole('combobox', {name: '用户提示词历史版本'});
  const dialog = page.getByRole('dialog');
  await dialog.evaluate(async el => { await Promise.all(el.getAnimations({subtree:true}).filter(a=>a.effect?.getComputedTiming().iterations !== Infinity).map(a=>a.finished)); });
  const size = await dialog.boundingBox();
  await history.click();
  await page.getByRole('option', {name: /^版本 1/}).click();
  await expect(page.getByRole('textbox', {name:'用户提示词可视化'})).toContainText('第一版描述');
  expect(await dialog.boundingBox()).toEqual(size);
  await page.getByRole('button', {name:'取消', exact:true}).click();
  expect((await (await page.request.get(`${url}/editor`)).json()).userPrompt).toBe('第二版描述');
  await open();
  await history.click();
  await page.getByRole('option', {name:/^版本 1/}).click();
  await page.getByRole('button', {name:'保存', exact:true}).click();
  await expect(dialog).toHaveCount(0);
  await openProject(page, project.title);
  await open();
  await expect(page.getByRole('textbox', {name:'用户提示词可视化'})).toContainText('第一版描述');
  const saved = await (await page.request.get(`${url}/editor`)).json();
  expect(saved.userPromptHistory.map((v: {prompt:string}) => v.prompt)).toEqual(['第一版描述', '第二版描述']);
});

 test("save version explicitly archives the current user prompt", async ({ page }) => {
  const project = await createProject(page, '手动存档');
  const root = `/api/v1/projects/${project.id}/tasks`;
  const task = await (await page.request.post(root, {data:{title:'任务', userPrompt:'手动版本'}})).json();
  await openProject(page, project.title);
  await page.locator('.task-list-row:not(.is-create)').first().dblclick();
  await page.getByRole('button', {name:'保存版本', exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const saved = await (await page.request.get(`${root}/${task.id}/editor`)).json();
  expect(saved.userPromptHistory.map((v: {prompt:string}) => v.prompt)).toEqual(['手动版本']);
 });
