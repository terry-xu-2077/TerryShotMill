import { describe, expect, it } from "vitest";

import { findAssetMention, insertAssetReference } from "./PromptAssetEditor";

describe("PromptAssetEditor helpers", () => {
  it("finds the active @ query at the caret", () => {
    expect(findAssetMention("镜头使用 @仓库", 8)).toEqual({ start: 5, end: 8, query: "仓库" });
    expect(findAssetMention("@旧港口 仓库", 7)).toEqual({ start: 0, end: 7, query: "旧港口 仓库" });
    expect(findAssetMention("@旧港口\n下一镜", 8)).toBeNull();
  });

  it("replaces only the active mention and preserves text after the caret", () => {
    const source = "使用 @仓库 保持雨夜";
    const mention = findAssetMention(source, 6);
    expect(mention).not.toBeNull();
    expect(insertAssetReference(source, mention!, "<Picture 1>")).toEqual({
      value: "使用 <Picture 1> 保持雨夜",
      caret: 14,
    });
  });
});
