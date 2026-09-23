import {expect,test} from "@playwright/test";
import {createProject,createTask,openProject} from "./helpers";

test("selecting a video version updates primary preview without confirmation",async({page})=>{
 const project=await createProject(page,"视频历史");
 const task=await createTask(page,project.id);
 let primary="new";
 await page.route(`**/projects/${project.id}/tasks/${task.id}/results`,route=>route.fulfill({json:{items:[{id:"new",createdAt:"2026-09-22T12:00:00Z"},{id:"old",createdAt:"2026-09-21T12:00:00Z"}]}}));
 await page.route(`**/projects/${project.id}/tasks/${task.id}/primary-result`,route=>{primary=route.request().postDataJSON().resultId;return route.fulfill({json:{id:primary}});});
 await page.route(`**/projects/${project.id}/workspace`,async route=>{
  const body=await(await route.fetch()).json();
  body.tasks[0].resultCount=2;
  body.tasks[0].primaryResult={id:primary,videoUrl:`/${primary}.mp4`,previewUrl:`/${primary}.png`};
  await route.fulfill({json:body});
 });
 await openProject(page,project.title);
 await page.locator('.task-list-row:not(.is-create)').first().click();
 const select=page.getByRole('combobox',{name:'视频历史版本'});
 const triggerBox=(await select.boundingBox())!;
 const hostBox=(await page.locator('.task-video-versions').boundingBox())!;
 expect(Math.abs(triggerBox.width-hostBox.width)).toBeLessThan(1);
 await select.click();
 await expect(select).toHaveCSS('border-radius','999px');
 await expect(page.getByRole('option').first().locator('strong')).toHaveCSS('white-space','nowrap');
 const heights=await page.getByRole('option').evaluateAll(items=>items.map(item=>item.getBoundingClientRect().height));
 expect(new Set(heights).size).toBe(1);
 await page.screenshot({path:'test-results/select-redesign.png'});
 await page.getByRole('option').filter({hasText:'版本 1'}).click();
 await expect.poll(()=>primary).toBe('old');
 await expect(page.locator('.task-info-preview .task-preview')).toHaveCSS('background-image',/old.png/);
 await expect(page.getByRole('dialog')).toHaveCount(0);
});
