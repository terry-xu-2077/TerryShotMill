import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApplicationSettingsPanel } from "./ApplicationSettingsPanel";

describe("ApplicationSettingsPanel", () => {
  it("keeps appearance separate from generation settings", async () => {
    const user = userEvent.setup();
    render(<ApplicationSettingsPanel onSave={vi.fn()} onClose={vi.fn()} />);
    await user.click(screen.getByRole("tab", { name: "外观" }));
    expect(screen.getByRole("region", { name: "外观设置" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "添加档位" })).not.toBeInTheDocument();
    expect(document.getElementById("comfyui-settings-title")).toBeNull();
  });
  it("separates connection and workflow configuration from AI settings without losing edits", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ApplicationSettingsPanel onSave={onSave} onClose={vi.fn()} />);
    await user.click(screen.getByRole("tab", { name: "API推理" }));
    await user.type(screen.getByLabelText("模型名称"), "local-model");
    await user.click(screen.getByRole("tab", { name: "ComfyUI 通信" }));
    expect(screen.getByLabelText("服务地址")).toBeVisible();
    expect(screen.queryByLabelText("模型名称")).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "生成工作流" }));
    expect(screen.getByRole("button", { name: "添加档位" })).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "AI 增强" }));
    expect(screen.getByLabelText("模型名称")).toHaveValue("local-model");
    await user.click(screen.getByRole("button", { name: "保存设置" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ providerMode: "api", apiModel: "local-model" }));
  });
});
