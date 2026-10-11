import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { OverlayProvider } from "../../ui/overlay";
import { lifecycleGateway } from "../../gateways/lifecycleGateway";
import type { ProjectSummary } from "../../gateways/projectGateway";
import { ProjectLifecycleBrowser, ProjectLifecycleConfirmation } from "./ProjectLifecycleBrowser";

const project = { id: "p", title: "项目", taskCount: 2, assetCount: 1 } as ProjectSummary;

it("shows current projects with direct removal and no archive or trash controls", async () => {
  const api = { ...lifecycleGateway, listProjects: vi.fn().mockResolvedValue([project]) };
  render(<OverlayProvider><ProjectLifecycleBrowser gateway={api} onClose={vi.fn()} onChanged={vi.fn()} /></OverlayProvider>);
  expect(await screen.findByRole("button", { name: "移除项目" })).toBeInTheDocument();
  expect(api.listProjects).toHaveBeenCalledWith();
  expect(screen.queryByText("归档")).not.toBeInTheDocument();
  expect(screen.queryByText("回收站")).not.toBeInTheDocument();
});

it("removes the project from recents after confirmation", async () => {
  const api = { ...lifecycleGateway, removeProject: vi.fn().mockResolvedValue(undefined) };
  const close = vi.fn();
  render(<OverlayProvider><ProjectLifecycleConfirmation gateway={api} project={project}
    onClose={close} onChanged={vi.fn().mockResolvedValue(undefined)} /></OverlayProvider>);
  await userEvent.click(screen.getByRole("button", { name: "确认移除" }));
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  expect(api.removeProject).toHaveBeenCalledWith("p");
});

it("retries refresh without deleting the project twice", async () => {
  const api = { ...lifecycleGateway, removeProject: vi.fn().mockResolvedValue(undefined) };
  const changed = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
  const close = vi.fn();
  render(<OverlayProvider><ProjectLifecycleConfirmation gateway={api} project={project}
    onClose={close} onChanged={changed} /></OverlayProvider>);
  await userEvent.click(screen.getByRole("button", { name: "确认移除" }));
  await userEvent.click(await screen.findByRole("button", { name: "重试刷新" }));
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  expect(api.removeProject).toHaveBeenCalledOnce();
  expect(changed).toHaveBeenCalledTimes(2);
});
