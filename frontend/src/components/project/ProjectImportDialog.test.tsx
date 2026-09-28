import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ProjectGatewayError } from "../../gateways/projectGateway";
import { OverlayProvider } from "../../ui/overlay";
import { ProjectImportDialog } from "./ProjectImportDialog";

const outcome = { projectId: "new-project", providerRequirements: [] };
function setup(importPackage = vi.fn().mockResolvedValue(outcome), onChanged = vi.fn().mockResolvedValue(undefined)) {
  const onClose = vi.fn();
  render(<OverlayProvider><ProjectImportDialog gateway={{ exportUrl: () => "", importPackage }}
    onChanged={onChanged} onClose={onClose} /></OverlayProvider>);
  return { importPackage, onChanged, onClose };
}
async function choose() {
  const file = new File(["package"], "project.zip", { type: "application/zip" });
  await userEvent.upload(screen.getByLabelText("项目 ZIP 包"), file);
  return file;
}

it("requires a file and refreshes once after successful import", async () => {
  const api = setup();
  expect(screen.getByRole("button", { name: "导入" })).toBeDisabled();
  const file = await choose();
  await userEvent.click(screen.getByRole("button", { name: "导入" }));
  expect(await screen.findByText("项目已导入")).toBeInTheDocument();
  expect(api.importPackage).toHaveBeenCalledExactlyOnceWith(file);
  expect(api.onChanged).toHaveBeenCalledOnce();
});

it("retries only refresh after the import has committed", async () => {
  const changed = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
  const api = setup(undefined, changed);
  await choose();
  await userEvent.click(screen.getByRole("button", { name: "导入" }));
  await userEvent.click(await screen.findByRole("button", { name: "重试刷新" }));
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(2));
  expect(api.importPackage).toHaveBeenCalledOnce();
});

it("allows explicit retry after a definite package rejection", async () => {
  const upload = vi.fn().mockRejectedValueOnce(new ProjectGatewayError("包已损坏", "INVALID", 422))
    .mockResolvedValue(outcome);
  setup(upload);
  await choose();
  await userEvent.click(screen.getByRole("button", { name: "导入" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("包已损坏");
  await userEvent.click(screen.getByRole("button", { name: "导入" }));
  expect(await screen.findByText("项目已导入")).toBeInTheDocument();
  expect(upload).toHaveBeenCalledTimes(2);
});

it("does not resubmit when a lost response leaves the result uncertain", async () => {
  const api = setup(vi.fn().mockRejectedValue(new TypeError("network error")));
  await choose();
  await userEvent.click(screen.getByRole("button", { name: "导入" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("避免重复创建项目");
  expect(screen.queryByRole("button", { name: "导入" })).not.toBeInTheDocument();
  expect(api.importPackage).toHaveBeenCalledOnce();
});

it("blocks closing and duplicate submission while importing", async () => {
  let complete!: (value: typeof outcome) => void;
  const upload = vi.fn(() => new Promise<typeof outcome>(resolve => { complete = resolve; }));
  const api = setup(upload);
  await choose();
  await userEvent.dblClick(screen.getByRole("button", { name: "导入" }));
  await userEvent.click(screen.getByRole("button", { name: "关闭对话框" }));
  await userEvent.keyboard("{Escape}");
  expect(api.onClose).not.toHaveBeenCalled();
  expect(upload).toHaveBeenCalledOnce();
  await act(async () => complete(outcome));
});
