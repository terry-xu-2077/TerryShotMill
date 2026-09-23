import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

const tokens = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8");

for (const mode of ["light", "dark"] as const) {
  test(`${mode} surfaces follow the selected palette across live changes`, async ({ page }) => {
    await page.setContent(`<html data-tc-mode="${mode}"><body>
      <div id="surface"></div>
    </body></html>`);
    await page.addStyleTag({ content: tokens });
    for (const base of ["#68717b", "#c9d8c4"]) {
      await page.evaluate(color => document.documentElement.style.setProperty("--tc-base", color), base);
      const colors = await page.evaluate(() => {
        const surface = document.getElementById("surface")!;
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 1;
        const ctx = canvas.getContext("2d")!;
        return ["--sm-bg", "--sm-surface-1", "--sm-surface-2", "--sm-surface-3", "--tc-panel", "--tc-surface-2"].map(token => {
          surface.style.backgroundColor = `var(${token})`;
          ctx.fillStyle = getComputedStyle(surface).backgroundColor;
          ctx.fillRect(0, 0, 1, 1);
          return { token, rgb: Array.from(ctx.getImageData(0, 0, 1, 1).data).slice(0, 3) };
        });
      });
      const baseRgb = [1, 3, 5].map(offset => parseInt(base.slice(offset, offset + 2), 16));
      const expected = mode === "light"
        ? baseRgb.map(channel => Math.round(channel * 0.16 + 255 * 0.84))
        : baseRgb;
      expect(colors[0].rgb, "light canvas mixes 16% base; dark uses base directly").toEqual(expected);
      if (mode === "light") {
        const surface = colors.find(color => color.token === "--sm-surface-1")!;
        const expectedSurface = baseRgb.map(channel => Math.round((channel * 0.16 + 255 * 0.84) * 0.12 + 255 * 0.88));
        expect(surface.rgb, "light panels preserve their original white mix").toEqual(expectedSurface);
      }
      for (const { token, rgb } of colors) {
        expect(Math.max(...rgb.map((channel, i) => Math.abs(channel - expected[i]))), token).toBeLessThanOrEqual(26);
      }
    }
  });
}
