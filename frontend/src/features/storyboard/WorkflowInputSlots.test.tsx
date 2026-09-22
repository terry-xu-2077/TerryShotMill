import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { mockProjectAssets } from "../../mock/assets";
import { WorkflowInputSlots } from "./WorkflowInputSlots";

it("explains why slots cannot load and retries without losing bindings", async () => {
  const user = userEvent.setup();
  const message = "无法连接 ComfyUI，请确认已启动；连接后重试读取槽位。";
  const load = vi.fn().mockRejectedValueOnce(new Error(message)).mockResolvedValueOnce([]);
  const change = vi.fn();
  render(<WorkflowInputSlots open workflowFile="w.json" bindings={[]} assets={mockProjectAssets} onChange={change} loadWorkflows={load} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  await user.click(screen.getByRole("button", { name: "重试读取输入槽位" }));
  expect(await screen.findByText("工作流槽位信息不可用")).toBeVisible();
  expect(change).not.toHaveBeenCalled();
});

it("combines asset categories with search and resets filters for a new slot selection", async () => {
  const user = userEvent.setup();
  const change = vi.fn();
  render(<WorkflowInputSlots open workflowFile="w.json" bindings={[]} assets={mockProjectAssets} onChange={change} loadWorkflows={async () => [{ id: "w.json", name: "测试", fileName: "w.json", relativePath: "w.json", format: "api", executable: true, hasShotmillBridge: true, inputs: [{ name: "image", type: "IMAGE", direction: "input", targetNodeId: "1", targetPort: "image", sourceNodeId: "2" }], outputs: [], warnings: [] }]} />);
  await user.click(await screen.findByRole("button", { name: /图片 1/ }));
  expect(screen.queryByRole("tab", { name: "仓库" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("tab", { name: "场景" }));
  expect(screen.getByRole("tab", { name: "场景" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("button", { name: "填入 旧港口仓库外景" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "填入 林澜 · 雨夜造型" })).not.toBeInTheDocument();
  await user.type(screen.getByPlaceholderText("搜索项目资产"), "不存在");
  await user.tab();
  expect(await screen.findByText("没有匹配的项目资产")).toBeVisible();
  await user.clear(screen.getByPlaceholderText("搜索项目资产"));
  await user.tab();
  await user.click(await screen.findByRole("button", { name: "填入 旧港口仓库外景" }));
  expect(change.mock.calls[0][1][0].assetId).toBe("asset-warehouse-exterior");
  await user.click(screen.getByRole("button", { name: /图片 1/ }));
  expect(screen.getByRole("tab", { name: "全部" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("button", { name: "填入 林澜 · 雨夜造型" })).toBeVisible();
});

it("shows asset management categories even when assets have no custom tags", async () => {
  const user = userEvent.setup();
  render(<WorkflowInputSlots open workflowFile="w.json" bindings={[]} assets={mockProjectAssets.map(asset => ({ ...asset, tags: [] }))} onChange={vi.fn()} loadWorkflows={async () => [{ id: "w.json", name: "测试", fileName: "w.json", relativePath: "w.json", format: "api", executable: true, hasShotmillBridge: true, inputs: [{ name: "image", type: "IMAGE", direction: "input", targetNodeId: "1", targetPort: "image", sourceNodeId: "2" }], outputs: [], warnings: [] }]} />);
  await user.click(await screen.findByRole("button", { name: /图片 1/ }));
  expect(screen.queryByRole("tab", { name: "仓库" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("tab", { name: "场景" }));
  expect(screen.getByRole("button", { name: "填入 旧港口仓库外景" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "填入 林澜 · 雨夜造型" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("tab", { name: "角色" }));
  expect(screen.getByRole("button", { name: "填入 林澜 · 雨夜造型" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "填入 旧港口仓库外景" })).not.toBeInTheDocument();
});
