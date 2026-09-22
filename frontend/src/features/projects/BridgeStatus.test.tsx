import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { BridgeStatus } from "./BridgeStatus";

it("distinguishes missing Bridge from connected and recovers on explicit retry", async () => {
  const load = vi.fn().mockResolvedValueOnce({ connected: true, bridgeNodeAvailable: false, message: "未安装" })
    .mockResolvedValue({ connected: true, bridgeNodeAvailable: true, message: "已连接" });
  render(<BridgeStatus load={load} />);
  await userEvent.click(await screen.findByRole("button", { name: "Bridge 未安装" }));
  expect(await screen.findByRole("button", { name: "Bridge 已连接" })).toBeInTheDocument();
  expect(load).toHaveBeenCalledTimes(2);
});

it("does not claim ComfyUI disconnected when the status request itself fails", async () => {
  render(<BridgeStatus load={vi.fn().mockRejectedValue(new Error("backend offline"))} />);
  expect(await screen.findByRole("button", { name: "Bridge 状态未知" })).toBeInTheDocument();
});

it("shows Bridge communication failure separately from missing installation", async () => {
  render(<BridgeStatus load={vi.fn().mockResolvedValue({ connected: true, bridgeNodeAvailable: false, bridgeState: "error", message: "Bridge timeout" })} />);
  expect(await screen.findByRole("button", { name: "Bridge 通信异常" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Bridge 未安装" })).not.toBeInTheDocument();
});
