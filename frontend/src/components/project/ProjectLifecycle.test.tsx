import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { OverlayProvider } from "../../ui/overlay";
import { lifecycleGateway } from "../../gateways/lifecycleGateway";
import type { ProjectSummary } from "../../gateways/projectGateway";
import { ProjectLifecycleConfirmation } from "./ProjectLifecycleBrowser";

const project = { id: "p", title: "项目", taskCount: 2, assetCount: 1 } as ProjectSummary;

it.each([true, false])("sends the project result retention choice: %s", async retain => {
  const api = { ...lifecycleGateway, purgeProject: vi.fn().mockResolvedValue({ archivedResultCount: 2 }) };
  const close = vi.fn();
  render(<OverlayProvider><ProjectLifecycleConfirmation gateway={api} intent={{ project, action: "purge" }}
    onClose={close} onChanged={vi.fn().mockResolvedValue(undefined)} /></OverlayProvider>);
  const checkbox = screen.getByRole("checkbox", { name: "归档全部生成结果后删除" });
  expect(checkbox).toBeChecked();
  expect(screen.getByText(/保留所有生成版本，可从首页/)).toBeInTheDocument();
  if (!retain) await userEvent.click(checkbox);
  if (!retain) expect(screen.getByText("未归档的全部生成结果也将永久删除。")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "永久删除项目" }));
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  expect(api.purgeProject).toHaveBeenCalledWith("p", retain);
});

it("retains the project dialog and selection when archiving fails", async () => {
  const api = { ...lifecycleGateway, purgeProject: vi.fn().mockRejectedValue(new Error("归档空间不足")) };
  const close = vi.fn();
  render(<OverlayProvider><ProjectLifecycleConfirmation gateway={api} intent={{ project, action: "purge" }}
    onClose={close} onChanged={vi.fn()} /></OverlayProvider>);
  await userEvent.click(screen.getByRole("button", { name: "永久删除项目" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("归档空间不足");
  expect(close).not.toHaveBeenCalled();
  expect(screen.getByRole("checkbox", { name: "归档全部生成结果后删除" })).toBeChecked();
});

it("retries refresh without deleting the project twice", async () => {
  const api = { ...lifecycleGateway, purgeProject: vi.fn().mockResolvedValue({}) };
  const changed = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
  const close = vi.fn();
  render(<OverlayProvider><ProjectLifecycleConfirmation gateway={api} intent={{ project, action: "purge" }}
    onClose={close} onChanged={changed} /></OverlayProvider>);
  await userEvent.click(screen.getByRole("button", { name: "永久删除项目" }));
  await userEvent.click(await screen.findByRole("button", { name: "重试刷新" }));
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  expect(api.purgeProject).toHaveBeenCalledOnce();
  expect(changed).toHaveBeenCalledTimes(2);
});
