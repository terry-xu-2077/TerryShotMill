import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { OverlayProvider } from "../../ui/overlay";
import { ProjectExportDialog } from "./ProjectExportDialog";

function setup() {
  const gateway = {
    prepareExport: vi.fn().mockResolvedValue({ token: "ready", expiresInSeconds: 300 }),
    downloadUrl: vi.fn(token => `/download/${token}`),
    discardExport: vi.fn().mockResolvedValue(undefined),
  };
  const onClose = vi.fn();
  const view = render(<OverlayProvider><ProjectExportDialog project={{ id: "p", title: "项目" }}
    gateway={gateway} onClose={onClose} /></OverlayProvider>);
  return { gateway, onClose, ...view };
}

it("prepares before offering a native download and discards unclaimed packages", async () => {
  const { gateway, unmount } = setup();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "打包项目" }));
  expect(await screen.findByRole("link", { name: "下载 ZIP" })).toHaveAttribute("href", "/download/ready");
  expect(gateway.prepareExport).toHaveBeenCalledExactlyOnceWith("p");
  unmount();
  expect(gateway.discardExport).toHaveBeenCalledExactlyOnceWith("ready");
});

it("does not delete a claimed download or pretend that it completed", async () => {
  const { gateway, unmount } = setup();
  await userEvent.click(screen.getByRole("button", { name: "打包项目" }));
  const link = await screen.findByRole("link", { name: "下载 ZIP" });
  link.addEventListener("click", event => event.preventDefault());
  await userEvent.click(link);
  expect(screen.getByRole("status")).toHaveTextContent("请在下载列表确认是否完成");
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  unmount();
  expect(gateway.discardExport).not.toHaveBeenCalled();
});

it("shows preparation failures and permits explicit retry", async () => {
  const { gateway } = setup();
  gateway.prepareExport.mockRejectedValueOnce(new Error("磁盘空间不足"));
  await userEvent.click(screen.getByRole("button", { name: "打包项目" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("磁盘空间不足");
  await userEvent.click(screen.getByRole("button", { name: "打包项目" }));
  await waitFor(() => expect(screen.getByRole("link", { name: "下载 ZIP" })).toBeInTheDocument());
  expect(gateway.prepareExport).toHaveBeenCalledTimes(2);
});
