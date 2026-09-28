import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { OverlayProvider } from "../../ui/overlay";
import { AssetImportPicker } from "./AssetImportPicker";
import type { ImportCandidate } from "../../gateways/assetTransferGateway";

it("selects assets, generated versions and archived results without copying before save", async () => {
  const items: ImportCandidate[] = (["asset", "result", "archive"] as const).map(kind => ({
    kind, id: kind, name: kind, sourceProjectId: "source", sourceProjectTitle: "来源", mediaType: "video",
    previewUrl: null, createdAt: "2026-09-27T00:00:00Z",
  }));
  const api = { candidates: vi.fn().mockResolvedValue(items), importSources: vi.fn() };
  const select = vi.fn(); const close = vi.fn();
  render(<OverlayProvider><AssetImportPicker projectId="target" gateway={api} onSelect={select} onClose={close} /></OverlayProvider>);
  const checks = await screen.findAllByRole("checkbox");
  for (const checkbox of checks) await userEvent.click(checkbox);
  await userEvent.click(screen.getByRole("button", { name: "加入项目草稿" }));
  expect(select).toHaveBeenCalledWith(items);
  expect(close).toHaveBeenCalledOnce();
  expect(api.importSources).not.toHaveBeenCalled();
});

it("does not submit stale choices after a load failure and can retry", async () => {
  const api = { candidates: vi.fn().mockRejectedValueOnce(new Error("加载失败")).mockResolvedValue([]), importSources: vi.fn() };
  render(<OverlayProvider><AssetImportPicker projectId="target" gateway={api} onSelect={vi.fn()} onClose={vi.fn()} /></OverlayProvider>);
  expect(await screen.findByRole("alert")).toHaveTextContent("加载失败");
  expect(screen.getByRole("button", { name: "加入项目草稿" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(await screen.findByText("没有可导入的资产或生成结果。")).toBeVisible();
});
