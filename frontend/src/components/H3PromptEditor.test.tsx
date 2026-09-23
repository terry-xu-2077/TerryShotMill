import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";

import { OverlayProvider } from "../ui/overlay";
import { H3PromptEditor } from "./H3PromptEditor";
import type { PromptAsset } from "./PromptAssetEditor";

const assets: PromptAsset[] = [
  {
    id: "asset-1",
    name: "林澜 · 雨夜造型",
    kind: "subject",
    reference: "<Subject 1>",
    detail: "角色素材",
    tone: "amber",
  },
  {
    id: "asset-2",
    name: "旧港口仓库外景",
    kind: "picture",
    reference: "<Picture 1>",
    detail: "场景素材",
    tone: "blue",
  },
];

function Harness({ initialValue = "仓库门口 " }: { initialValue?: string }) {
  const [value, setValue] = useState(initialValue);
  return (
    <OverlayProvider>
      <H3PromptEditor
        value={value}
        onChange={setValue}
        assets={assets}
        ariaLabel="用户提示词"
        viewMode="visual"
      />
      <output data-testid="prompt-value">{value}</output>
    </OverlayProvider>
  );
}

describe("H3PromptEditor visual asset mentions", () => {
  it("keeps the asset menu closed after the Escape key is released", () => {
    render(<Harness />);
    const editor = screen.getByRole("textbox", { name: "用户提示词可视化" });
    editor.textContent = "仓库门口 @";
    const range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(false);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    fireEvent.input(editor);
    expect(screen.getByRole("listbox", { name: "引用任务资产" })).toBeInTheDocument();
    fireEvent.keyDown(editor, { key: "Escape" });
    fireEvent.keyUp(editor, { key: "Escape" });
    expect(screen.queryByRole("listbox", { name: "引用任务资产" })).not.toBeInTheDocument();
    expect(screen.getByTestId("prompt-value")).toHaveTextContent("仓库门口 @");
  });

  it("does not replace dialogue controls when focus moves within the editor", () => {
    render(<Harness initialValue="(S1) <d>[Chinese] 再撑一段。</d>" />);
    const editor = screen.getByRole("textbox", { name: "用户提示词可视化" });
    const language = screen.getByRole("combobox", { name: "对白语言" });
    const dialogue = editor.querySelector(".h3-dialogue-text")!;
    fireEvent.blur(dialogue, { relatedTarget: language });
    expect(screen.getByRole("combobox", { name: "对白语言" })).toBe(language);
    expect(dialogue.isConnected).toBe(true);
    fireEvent.change(language, { target: { value: "English" } });
    expect(screen.getByTestId("prompt-value")).toHaveTextContent("(S1) <d>[English] 再撑一段。</d>");
  });

  it("can edit a dialogue again after focus has left the visual editor", () => {
    render(<Harness initialValue="(S1) <d>[Chinese] 再撑一段。</d>" />);
    fireEvent.blur(screen.getByRole("textbox", { name: "用户提示词可视化" }));
    fireEvent.change(screen.getByRole("combobox", { name: "对白语言" }), { target: { value: "English" } });
    expect(screen.getByTestId("prompt-value")).toHaveTextContent("(S1) <d>[English] 再撑一段。</d>");
  });

  it("typing @ opens the asset menu and inserts the selected reference", () => {
    render(<Harness />);
    const editor = screen.getByRole("textbox", { name: "用户提示词可视化" });

    editor.textContent = "仓库门口 @";
    const range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(false);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    fireEvent.input(editor);

    expect(screen.getByRole("listbox", { name: "引用任务资产" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("option", { name: /林澜 · 雨夜造型/ }));

    expect(screen.getByTestId("prompt-value")).toHaveTextContent("仓库门口 <Subject 1>");
  });
});

it("inserts an editable dialogue from the slash menu", () => {
  render(<Harness />);
  const editor = screen.getByRole("textbox", { name: "用户提示词可视化" });
  editor.textContent = "他说/";
  const range = document.createRange(); range.selectNodeContents(editor); range.collapse(false);
  window.getSelection()?.removeAllRanges(); window.getSelection()?.addRange(range);
  fireEvent.input(editor);
  fireEvent.click(screen.getByRole("option", { name: /对白块/ }));
  expect(screen.getByTestId("prompt-value")).toHaveTextContent("他说<d>[Chinese] </d>");
  expect(screen.getByRole("combobox", { name: "对白语言" })).toBeInTheDocument();
  const body = editor.querySelector(".h3-dialogue-text")!;
  body.textContent = "你好"; fireEvent.input(body);
  expect(screen.getByTestId("prompt-value")).toHaveTextContent("<d>[Chinese] 你好</d>");
});
it("replaces only the clicked asset reference", () => {
  render(<Harness initialValue="<Picture 1> 与 <Picture 1>。" />);
  fireEvent.click(screen.getAllByRole("button", { name: "更换资产：旧港口仓库外景" })[1]);
  fireEvent.click(screen.getByRole("option", { name: /林澜/ }));
  expect(screen.getByTestId("prompt-value")).toHaveTextContent("<Picture 1> 与 <Subject 1>。");
});
