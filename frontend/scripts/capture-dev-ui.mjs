import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "@playwright/test";

const baseURL = process.env.SHOTMILL_UI_URL ?? "http://127.0.0.1:1420";
const output = resolve("../.artifacts/ui-current");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: "chrome" });
try {
  for (const mode of ["light", "dark"]) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    await page.addInitScript(theme => localStorage.setItem("shotmill.color-theme", theme), mode);
    const capture = async name => {
      await page.evaluate(async () => {
        await document.fonts.ready;
        await Promise.all(document.getAnimations().filter(animation =>
          Number.isFinite(animation.effect?.getComputedTiming().endTime)
        ).map(animation => animation.finished.catch(() => {})));
      });
      await page.screenshot({ path: resolve(output, `${mode}-${name}.png`), animations: "disabled" });
    };
    await page.goto(baseURL);
    await page.getByRole("main", { name: "项目首页" }).waitFor();
    await page.getByText("正在加载项目…", { exact: true }).waitFor({ state: "hidden" });
    await capture("home");
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await page.getByRole("tab", { name: "外观", exact: true }).click();
    await capture("appearance");
    await page.getByRole("button", { name: "关闭对话框", exact: true }).click();
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    const project = page.getByRole("button", { name: /^打开项目 / }).first();
    if (await project.count()) {
      await project.click();
      await page.getByRole("main", { name: "项目工作台" }).waitFor();
      await capture("workspace");
      const row = page.locator(".task-list-row:not(.is-create), .task-card-item").first();
      if (await row.count()) {
        await row.dblclick();
        await page.getByTestId("simple-task-editor").waitFor();
        await capture("task-editor");
      }
    }
    await page.close();
  }
  console.log(`Screenshots: ${output}`);
} finally {
  await browser.close();
}
