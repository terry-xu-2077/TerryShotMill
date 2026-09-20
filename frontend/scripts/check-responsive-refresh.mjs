import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "@playwright/test";

await mkdir("../.artifacts/ui-refresh", { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  for (const theme of ["light", "dark"]) {
  for (const viewport of [{ width: 1440, height: 960 }, { width: 1366, height: 768 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const capture = async (name) => {
      await page.evaluate(() => Promise.all(document.getAnimations().filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime)).map((animation) => animation.finished.catch(() => {}))));
      await page.screenshot({ path: `../.artifacts/ui-refresh/${theme}-${viewport.width}-${name}.png` });
      assert.ok(await page.evaluate(() => document.body.scrollWidth <= innerWidth), `${name}: horizontal overflow`);
    };
    await page.goto("http://127.0.0.1:1420");
    await page.getByRole("button", { name: "打开项目 异星边境", exact: true }).waitFor();
    await page.getByRole("button", { name: theme === "dark" ? "暗色" : "亮色", exact: true }).click();
    await page.reload();
    await page.getByRole("button", { name: "打开项目 异星边境", exact: true }).waitFor();
    assert.equal(await page.locator("html").getAttribute("data-tc-mode"), theme);
    await capture("home");
    await page.getByRole("button", { name: "打开项目 异星边境", exact: true }).click();
    await page.locator(".task-list-row.is-selected").waitFor();
    await capture("list");
    await page.getByRole("button", { name: "切换为卡片视图", exact: true }).click();
    await page.locator(".task-card-item").first().waitFor();
    await capture("cards");
    await page.locator(".task-card-item").first().dblclick();
    const dialog = page.getByRole("dialog");
    await dialog.waitFor();
    await dialog.evaluate((element) => Promise.all(element.getAnimations({ subtree: true }).map((animation) => animation.finished)));
    const initial = await dialog.boundingBox();
    await capture("editor");
    await page.getByRole("button", { name: "生成参数", exact: true }).click();
    await capture("parameters");
    const expanded = await dialog.boundingBox();
    assert.equal(expanded.width, initial.width);
    assert.equal(expanded.height, initial.height);
    const geometry = await page.evaluate(() => {
      const rect = (selector) => document.querySelector(selector).getBoundingClientRect();
      const head = rect(".simple-prompt-head");
      const body = rect(".simple-prompt-body");
      const actions = rect(".simple-task-editor-actions");
      return { headerBottom: head.bottom, bodyTop: body.top, actionsBottom: actions.bottom, viewportHeight: innerHeight };
    });
    assert.ok(geometry.headerBottom <= geometry.bodyTop + 1, "Header overlaps prompt body");
    assert.ok(geometry.actionsBottom <= geometry.viewportHeight, "Actions outside viewport");
    await page.getByRole("button", { name: "取消", exact: true }).click();
    await page.getByRole("button", { name: "项目配置", exact: true }).click();
    await capture("project-info");
    const configFrame = await page.getByRole("dialog").boundingBox();
    await page.getByRole("button", { name: "资产管理", exact: true }).click();
    await capture("project-assets");
    assert.deepEqual(await page.getByRole("dialog").boundingBox(), configFrame, "Project tabs resize dialog");
    const configGeometry = await page.evaluate(() => {
      const nodes = [".project-config-dialog-v2", ".project-asset-manager-v2", ".project-asset-meta", ".project-config-actions"];
      return nodes.map((selector) => {
        const el = document.querySelector(selector);
        const r = el.getBoundingClientRect();
        return { selector, width: el.clientWidth, scrollWidth: el.scrollWidth, bottom: r.bottom, right: r.right };
      });
    });
    for (const geometry of configGeometry) {
      assert.ok(geometry.scrollWidth <= geometry.width + 1, `${geometry.selector}: content overflows`);
      assert.ok(geometry.bottom <= viewport.height && geometry.right <= viewport.width, `${geometry.selector}: outside viewport`);
    }
    await page.getByRole("button", { name: "取消", exact: true }).click();
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await page.getByRole("dialog").waitFor();
    await capture("settings");
    await page.getByRole("tab", { name: "外观", exact: true }).click();
    assert.equal(await page.getByRole("dialog").getByRole("button", { name: theme === "dark" ? "暗色" : "亮色", exact: true }).getAttribute("aria-pressed"), "true");
    await capture("appearance");
    for (const name of ["ComfyUI 通信", "生成工作流"]) {
      await page.getByRole("tab", { name, exact: true }).click();
      if (name === "生成工作流") {
        await page.getByRole("button", { name: "读取工作流", exact: true }).click();
        await page.getByRole("button", { name: "读取工作流", exact: true }).waitFor();
      }
      await capture(`settings-${name === "生成工作流" ? "workflows" : "connection"}`);
      assert.ok(await page.getByRole("button", { name: "保存设置" }).isVisible());
    }
    assert.deepEqual(errors, []);
    console.log(`PASS ${theme} ${viewport.width}x${viewport.height}`);
    await page.close();
  }
  }
} finally {
  await browser.close();
}
