import { expect, test } from "@playwright/test";
import { textContrast } from "./contrast";

test("transparent ancestor opacity composites glyphs against the unchanged backdrop", async ({ page }) => {
  await page.setContent('<main style="background:white"><footer style="opacity:.5"><span style="color:black;opacity:.5">sample</span></footer></main>');
  const result = await textContrast(page.locator("span"));
  expect(result.foreground).toEqual([0, 0, 0, .25]);
  expect(result.backgrounds).toEqual([[255, 255, 255, 1]]);
  expect(result.minimumRatio).toBeCloseTo(1.834, 2);
});

for (const fill of ["gray", "rgba(0,0,0,.1)"]) test(`painted translucent groups reject ${fill} rather than falsely passing`, async ({ page }) => {
  await page.setContent('<main style="background:white"><footer style="opacity:.5"><span style="color:black;background:gray">sample</span></footer></main>');
  await page.locator("span").evaluate((el, color) => { el.style.background = color; }, fill);
  await expect(textContrast(page.locator("span"))).rejects.toThrow("Group opacity needs separate compositing review");
});
