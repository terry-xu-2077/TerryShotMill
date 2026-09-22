import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApplicationSettingsPanel } from "./ApplicationSettingsPanel";

describe("ApplicationSettingsPanel", () => {
  it("saves a named workflow preset with a description directly", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(<ApplicationSettingsPanel onSave={onSave} onClose={onClose} onRefreshComfyUIWorkflows={async () => [{
      id: "dialogue", name: "对白工作流", fileName: "dialogue.json", relativePath: "dialogue.json", format: "canvas",
      executable: true, hasShotmillBridge: true, inputs: [{ name: "帧数", direction: "input", type: "INT", targetNodeId: "7", targetPort: "frames", sourceNodeId: "2" }], outputs: [], warnings: [],
    }]} />);
    await user.click(screen.getByRole("tab", { name: "生成工作流" }));
    await user.click(screen.getByRole("button", { name: "读取工作流" }));
    await user.click(screen.getByRole("combobox", { name: "预设工作流" }));
    await user.click(screen.getByRole("option", { name: "对白工作流" }));
    await user.type(screen.getByRole("textbox", { name: "档位名称" }), "人物近景");
    await user.type(screen.getByRole("textbox", { name: "档位简介" }), "双人对白和面部特写");
    await user.click(screen.getByRole("combobox", { name: "帧数 · frames来源" }));
    await user.click(screen.getByRole("option", { name: "按总秒数换算帧数" }));
    await user.clear(screen.getByRole("textbox", { name: "帧数倍数" }));
    await user.type(screen.getByRole("textbox", { name: "帧数倍数" }), "4");
    await user.clear(screen.getByRole("textbox", { name: "帧数偏移" }));
    await user.type(screen.getByRole("textbox", { name: "帧数偏移" }), "1");
    await user.click(screen.getByRole("button", { name: "保存档位预设" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ comfyui: expect.objectContaining({ workflowProfiles: [expect.objectContaining({
      name: "人物近景", description: "双人对白和面部特写", workflowFile: "dialogue.json",
      numericBindings: [{ portId: "7:frames:2", source: "frameCount", fps: 24, frameMultiple: 4, frameOffset: 1, value: null }],
    })] }) }));
    expect(onClose).not.toHaveBeenCalled();
  });
  it("keeps appearance separate from generation settings", async () => {
    const user = userEvent.setup();
    render(<ApplicationSettingsPanel onSave={vi.fn()} onClose={vi.fn()} />);
    await user.click(screen.getByRole("tab", { name: "外观" }));
    expect(screen.getByRole("region", { name: "外观设置" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "新建档位" })).not.toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: "新建档位" })).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "AI 增强" }));
    expect(screen.getByLabelText("模型名称")).toHaveValue("local-model");
    await user.click(screen.getByRole("button", { name: "保存设置" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ providerMode: "api", apiModel: "local-model" }));
  });
});
