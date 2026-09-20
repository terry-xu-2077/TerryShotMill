import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import type { GenerationTask } from "../../domain/storyboard";
import { mockProjectAssets } from "../../mock/assets";
import { mockStoryboard } from "../../mock/storyboard";
import type { PromptEnhancementRequest, PromptEnhancementResponse } from "../../services/promptEnhancement";
import { OverlayProvider } from "../../ui/overlay";
import { TaskEditorDialog } from "./TaskEditorDialog";

const inputWorkflow = {
  id: "test.json", name: "Test", fileName: "test.json", relativePath: "test.json", format: "canvas", executable: true, hasShotmillBridge: true, outputs: [], warnings: [],
  inputs: [
    { name: "图片 1", direction: "input", type: "IMAGE", targetNodeId: "9", targetPort: "image_0" },
    { name: "图片 2", direction: "input", type: "IMAGE", targetNodeId: "9", targetPort: "image_1" },
    { name: "视频 1", direction: "input", type: "VIDEO", targetNodeId: "9", targetPort: "video_0" },
    { name: "音频 1", direction: "input", type: "AUDIO", targetNodeId: "9", targetPort: "audio_0" },
  ],
};

function renderEditor(
  onSave = vi.fn(),
  onClose = vi.fn(),
  task?: GenerationTask,
  onEnhancePrompt: (request: PromptEnhancementRequest) => Promise<PromptEnhancementResponse> = vi.fn(async () => ({
    id: "ai-default",
    createdAt: "2026-09-13T08:00:00+08:00",
    prompt: "默认 AI 增强提示词",
  })),
) {
  return {
    onSave,
    onClose,
    ...render(
      <OverlayProvider>
        <TaskEditorDialog
          open
          task={task ?? structuredClone(mockStoryboard.tasks[0])}
          assets={mockProjectAssets}
          workflowProfiles={[{ id: "test", name: "测试工作流", resolution: "720p", quality: "标准", enabled: true, workflowFile: "test.json" }]}
          onLoadWorkflows={async () => [inputWorkflow]}
          previousTaskDurationSeconds={15}
          previousTaskSummary="上一任务中，角色穿过雨夜码头并抵达仓库外。"
          projectContext={{ description: "雨夜旧港口项目背景", useDescriptionForAiPrompt: true }}
          onEnhancePrompt={onEnhancePrompt}
          onClose={onClose}
          onSave={onSave}
        />
      </OverlayProvider>,
    ),
  };
}

describe("TaskEditorDialog", () => {
  it("keeps the draft open with a recoverable error when saving fails", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
    const { onClose } = renderEditor(onSave);
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("保存失败");
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(onSave.mock.calls[1][0]).toEqual(onSave.mock.calls[0][0]);
  });

  it("does not assign an unbound project character to an AI logical subject", async () => {
    const user = userEvent.setup();
    const task = structuredClone(mockStoryboard.tasks[0]);
    task.assetBindings = [{ assetId: "asset-warehouse-exterior", role: "reference", reference: "<Picture 1>" }];
    task.aiPrompt = "subject_definitions: <Subject 1> is the building in <Picture 1>.";
    task.generationParams = { promptSource: "ai", userPrompt: "仓库" };
    const { onSave } = renderEditor(vi.fn(), vi.fn(), task);
    const editor = screen.getByRole("textbox", { name: "AI 增强提示词可视化" });
    expect(within(editor).queryByRole("img", { name: "林澜 · 雨夜造型" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(onSave.mock.calls[0][0].assetBindings).toEqual(task.assetBindings);
  });

  it("selects an enabled configured workflow and saves its stable id with duration", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<OverlayProvider><TaskEditorDialog open task={structuredClone(mockStoryboard.tasks[0])} assets={[]} onClose={vi.fn()} onSave={onSave}
      defaultWorkflowProfileId="standard" workflowProfiles={[
        { id: "standard", name: "标准视频", resolution: "720p", quality: "标准", workflowFile: "standard.json", enabled: true },
        { id: "detail", name: "精细视频", resolution: "1080p", quality: "高质量", workflowFile: "detail.json", enabled: true },
        { id: "off", name: "停用视频", resolution: "", quality: "", workflowFile: "off.json", enabled: false },
      ]} /></OverlayProvider>);
    await user.click(screen.getByRole("button", { name: "生成参数" }));
    expect(screen.queryByRole("tablist", { name: "分辨率" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tablist", { name: "质量档位" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "生成工作流" }));
    expect(screen.queryByRole("option", { name: "停用视频" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "精细视频" }));
    fireEvent.change(screen.getByRole("slider", { name: "总秒数" }), { target: { value: "12" } });
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ plannedDurationSeconds: 12, generationParams: expect.objectContaining({ workflowProfileId: "detail", resolution: "1080p", quality: "高质量" }) }));
  });
  it("preserves imported bindings and their order when prompts contain no inline references", async () => {
    const user = userEvent.setup();
    const task = structuredClone(mockStoryboard.tasks[0]);
    task.assetBindings = [
      { assetId: "asset-warehouse-exterior", role: "reference", reference: "<Picture 1>", notes: "port-a" },
      { assetId: "asset-character-linlan", role: "character", reference: "<Subject 1>" },
    ];
    task.aiPrompt = "";
    task.generationParams = { userPrompt: "角色走入仓库", promptSource: "user" };
    const { onSave } = renderEditor(vi.fn(), vi.fn(), task);
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(onSave.mock.calls[0][0].assetBindings).toEqual(task.assetBindings);
  });

  it("includes explicitly bound media in enhancement even without inline references", async () => {
    const user = userEvent.setup();
    const task = structuredClone(mockStoryboard.tasks[0]);
    task.assetBindings = [{ assetId: "asset-character-linlan", role: "character", reference: "<Subject 1>" }];
    task.aiPrompt = "";
    task.generationParams = { userPrompt: "角色走入仓库", promptSource: "user" };
    const enhance = vi.fn(async (_request: PromptEnhancementRequest) => ({ id: "enhanced-bound", createdAt: "", prompt: "角色走入仓库，镜头前推" }));
    renderEditor(vi.fn(), vi.fn(), task, enhance);
    await user.click(screen.getByRole("tab", { name: /AI 增强/ }));
    await user.click(screen.getByRole("button", { name: "增强" }));
    expect(enhance.mock.calls[0][0]).toMatchObject({ assets: [{ id: "asset-character-linlan", reference: "<Subject 1>" }] });
  });

  it("keeps a filled slot when only its prompt mention is removed", async () => {
    const user = userEvent.setup();
    const task = structuredClone(mockStoryboard.tasks[0]);
    task.assetBindings = [{ assetId: "asset-character-linlan", role: "character", reference: "<Subject 1>" }];
    task.aiPrompt = "";
    task.generationParams = { userPrompt: "<Subject 1> 走入仓库", promptSource: "user", userPromptViewMode: "text" };
    const { onSave } = renderEditor(vi.fn(), vi.fn(), task);
    await user.clear(screen.getByRole("textbox", { name: "用户提示词" }));
    await user.type(screen.getByRole("textbox", { name: "用户提示词" }), "空仓库");
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(onSave.mock.calls[0][0].assetBindings).toEqual(task.assetBindings);
  });

  it("reserves existing reference numbers and keeps binding roles when adding another asset", async () => {
    const user = userEvent.setup();
    const task = structuredClone(mockStoryboard.tasks[0]);
    task.assetBindings = [{ assetId: "asset-warehouse-exterior", role: "character", reference: "<Subject 1>", notes: "original-port" }];
    task.aiPrompt = "";
    task.generationParams = { userPrompt: "<Subject 1> ", promptSource: "user", userPromptViewMode: "text" };
    const { onSave } = renderEditor(vi.fn(), vi.fn(), task);
    await user.click(await screen.findByRole("button", { name: /图片 2 · image_1/ }));
    await user.click(screen.getByRole("button", { name: "填入 林澜 · 雨夜造型" }));
    await user.type(screen.getByRole("textbox", { name: "用户提示词" }), "@");
    await user.click(within(screen.getByRole("listbox", { name: "引用任务资产" })).getByRole("option", { name: /林澜 · 雨夜造型/ }));
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(onSave.mock.calls[0][0].assetBindings).toEqual([
      expect.objectContaining({ assetId: task.assetBindings[0].assetId, reference: "<Subject 1>" }),
      { assetId: "asset-character-linlan", role: "character", reference: "<Picture 2>" },
    ]);
  });
  it("keeps parameters collapsed by default and preserves edits when folding", async () => {
    const user = userEvent.setup();
    const { onSave } = renderEditor();
    const toggle = screen.getByRole("button", { name: "生成参数" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("tablist", { name: "分辨率" })).not.toBeInTheDocument();
    await user.click(toggle);
    fireEvent.change(screen.getByRole("slider", { name: "总秒数" }), { target: { value: "12" } });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(onSave.mock.calls[0][0].plannedDurationSeconds).toBe(12);
  });

  it("uses one workflow dropdown while preserving duration and continuation controls", async () => {
    renderEditor();
    await screen.findByRole("list", { name: "媒体输入槽位" });
    fireEvent.click(screen.getByRole("button", { name: "生成参数" }));

    const dialog = screen.getByRole("dialog", { name: /抵达仓库并发现门内异常/ });
    expect(within(dialog).getByTitle("编辑任务名称")).toBeInTheDocument();
    expect(within(dialog).getByText("任务编号 T01-001")).toBeInTheDocument();
    expect(within(dialog).queryByRole("tablist", { name: "分辨率" })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("tablist", { name: "质量档位" })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("combobox", { name: "生成工作流" })).toHaveTextContent("测试工作流");
    expect(within(dialog).getByRole("tablist", { name: "生成模式" })).toHaveClass("tc-segmented");
    expect(within(dialog).getByRole("tablist", { name: "上下文承接方式" })).toHaveClass("tc-segmented");
    expect(within(dialog).getByRole("slider", { name: "总秒数" })).toBeInTheDocument();
    expect(within(dialog).getByRole("slider", { name: "承接起点" })).toBeInTheDocument();
    expect(within(dialog).getByRole("slider", { name: "承接终点" })).toBeInTheDocument();
    expect(within(dialog).getByRole("tab", { name: "片段承接" })).toHaveAttribute("aria-selected", "true");
    expect(within(dialog).getByRole("tab", { name: "用户" })).toBeInTheDocument();
    expect(within(dialog).getByRole("tab", { name: /AI 增强/ })).toBeInTheDocument();
    expect(dialog.querySelectorAll(".tc-sliding-tabs").length).toBe(0);
    expect(dialog.querySelectorAll(".tc-segmented").length).toBeGreaterThanOrEqual(2);
    expect(dialog).not.toHaveTextContent("Generation Profile");
    expect(dialog).not.toHaveTextContent("Visual Beat");
    expect(dialog).not.toHaveTextContent("Validator");
  });

  it("edits task name and saves duration plus continuation interval", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const onClose = vi.fn();
    renderEditor(onSave, onClose);

    await user.click(screen.getByTitle("编辑任务名称"));
    const nameInput = screen.getByRole("textbox", { name: "任务名称" });
    await user.clear(nameInput);
    await user.type(nameInput, "雨夜抵达仓库");
    await user.keyboard("{Enter}");

    await user.click(screen.getByRole("tab", { name: /文本/ }));
    const prompt = screen.getByRole("textbox", { name: "用户提示词" });
    await user.clear(prompt);
    await user.type(prompt, "主角走入仓库，保持雨夜连续性。");

    await user.click(screen.getByRole("button", { name: "生成参数" }));
    fireEvent.change(screen.getByRole("slider", { name: "总秒数" }), { target: { value: "9" } });
    fireEvent.change(screen.getByRole("slider", { name: "承接起点" }), { target: { value: "11" } });
    fireEvent.change(screen.getByRole("slider", { name: "承接终点" }), { target: { value: "15" } });

    await user.click(screen.getByRole("button", { name: "保存" }));

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0]).toMatchObject({
      title: "雨夜抵达仓库",
      finalPrompt: "主角走入仓库，保持雨夜连续性。",
      plannedDurationSeconds: 9,
      generationParams: {
        contextMode: "片段承接",
        contextStartSeconds: 11,
        contextEndSeconds: 15,
        contextDurationSeconds: 4,
        promptSource: "user",
        userPromptViewMode: "text",
      },
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("defaults a new continuation interval to the last one second of the previous task", () => {
    const task = structuredClone(mockStoryboard.tasks[0]);
    task.generationParams = {
      ...task.generationParams,
      contextMode: "片段承接",
    };
    delete task.generationParams.contextDurationSeconds;
    delete task.generationParams.contextStartSeconds;
    delete task.generationParams.contextEndSeconds;

    renderEditor(vi.fn(), vi.fn(), task);
    fireEvent.click(screen.getByRole("button", { name: "生成参数" }));

    expect(screen.getByRole("slider", { name: "承接起点" })).toHaveValue("14");
    expect(screen.getByRole("slider", { name: "承接终点" })).toHaveValue("15");
    expect(screen.getByText("14s – 15s · 1s")).toBeInTheDocument();
  });

  it("switches context mode with tabs instead of a select", async () => {
    const user = userEvent.setup();
    renderEditor();
    await user.click(screen.getByRole("button", { name: "生成参数" }));

    await user.click(screen.getByRole("tab", { name: "尾帧承接" }));
    expect(screen.getByText("使用上一任务最终帧作为本任务的起始视觉参考。")).toBeInTheDocument();
    expect(screen.queryByRole("slider", { name: "承接起点" })).not.toBeInTheDocument();
  });

  it("gives both user and AI prompts independent visual and text view modes", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    renderEditor(onSave);

    expect(screen.getByRole("textbox", { name: "用户提示词可视化" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /文本/ }));
    expect(screen.getByRole("textbox", { name: "用户提示词" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /AI 增强/ }));
    expect(screen.getByRole("textbox", { name: "AI 增强提示词可视化" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "工作流输入资产" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /文本/ }));
    expect(screen.getByRole("textbox", { name: "AI 增强提示词" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "用户" }));
    expect(screen.getByRole("tab", { name: /文本/ })).toHaveAttribute("aria-selected", "true");

    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(onSave.mock.calls[0][0].generationParams).toMatchObject({
      userPromptViewMode: "text",
      aiPromptViewMode: "text",
    });
  });

  it("shows AI history only on the AI tab and creates repeatable enhancement versions from summary context", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const onEnhancePrompt = vi.fn()
      .mockResolvedValueOnce({ id: "ai-v1", createdAt: "2026-09-13T08:10:00+08:00", prompt: "AI增强版本一", taskRevision: 8 })
      .mockResolvedValueOnce({ id: "ai-v2", createdAt: "2026-09-13T08:12:00+08:00", prompt: "AI增强版本二", taskRevision: 9 });
    const task = structuredClone(mockStoryboard.tasks[0]);
    task.aiPrompt = "";
    task.finalPrompt = "用户原始提示词";
    task.generationParams = {
      ...task.generationParams,
      userPrompt: "用户原始提示词",
      promptSource: "user",
      aiPromptHistory: [],
    };

    renderEditor(onSave, vi.fn(), task, onEnhancePrompt);

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /AI 增强/ }));

    let history = screen.getByRole("combobox");
    expect(history).toBeDisabled();
    expect(screen.getByText("点击右下角“增强”，基于用户提示词生成一个新的增强版本。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "增强" }));
    await waitFor(() => expect(onEnhancePrompt).toHaveBeenCalledTimes(1));
    expect(onEnhancePrompt.mock.calls[0][0]).toMatchObject({
      userPrompt: "用户原始提示词",
      previousTaskSummary: "上一任务中，角色穿过雨夜码头并抵达仓库外。",
      projectBackground: "雨夜旧港口项目背景",
    });
    history = screen.getByRole("combobox");
    expect(history).not.toBeDisabled();
    expect(history).toHaveAttribute("data-value", "ai-v1");
    await waitFor(() => expect(screen.getByRole("textbox", { name: "AI 增强提示词可视化" })).toHaveTextContent("AI增强版本一"));

    await user.click(screen.getByRole("button", { name: "增强" }));
    await waitFor(() => expect(onEnhancePrompt).toHaveBeenCalledTimes(2));
    history = screen.getByRole("combobox");
    expect(history).toHaveAttribute("data-value", "ai-v2");
    await user.click(history);
    const historyList = screen.getByRole("listbox");
    const historyOptions = within(historyList).getAllByRole("option");
    expect(historyOptions).toHaveLength(2);
    await user.click(historyOptions[0]);
    await waitFor(() => expect(screen.getByRole("textbox", { name: "AI 增强提示词可视化" })).toHaveTextContent("AI增强版本一"));
    expect(screen.getByRole("combobox")).toHaveAttribute("data-value", "ai-v1");
    await user.click(screen.getByRole("button", { name: "保存" }));

    expect(onSave.mock.calls[0][0]).toMatchObject({
      aiPrompt: "AI增强版本一",
      finalPrompt: "AI增强版本一",
      generationParams: {
        promptSource: "ai",
        selectedAiPromptHistoryId: "ai-v1",
        revision: 9,
      },
    });
    expect(onSave.mock.calls[0][0].generationParams.aiPromptHistory).toHaveLength(2);
  });

  it("requires filling a slot before @ offers that asset and preserves empty earlier slots", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const task = structuredClone(mockStoryboard.tasks[0]);
    task.assetBindings = [];
    task.finalPrompt = "";
    task.generationParams = { ...task.generationParams, userPrompt: "", promptSource: "user" };
    renderEditor(onSave, vi.fn(), task);

    await user.click(screen.getByRole("tab", { name: /文本/ }));
    const prompt = screen.getByRole("textbox", { name: "用户提示词" });
    await user.clear(prompt);
    await user.type(prompt, "使用 @");
    expect(within(screen.getByRole("listbox", { name: "引用任务资产" })).queryByRole("option")).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(await screen.findByRole("button", { name: /图片 2 · image_1/ }));
    await user.click(screen.getByRole("button", { name: "填入 林澜 · 雨夜造型" }));
    await user.clear(prompt);
    await user.type(prompt, "使用 @");
    const menu = screen.getByRole("listbox", { name: "引用任务资产" });
    await user.click(within(menu).getByRole("option", { name: /林澜 · 雨夜造型/ }));
    await user.click(screen.getByRole("button", { name: "保存" }));

    expect(onSave.mock.calls[0][0]).toMatchObject({
      finalPrompt: "使用 <Picture 2> ",
      assetBindings: [{
        assetId: "asset-character-linlan",
        role: "character",
        reference: "<Picture 2>",
      }],
    });
    expect(onSave.mock.calls[0][0].generationParams.workflowInputs.slots).toEqual([
      { portId: "9:image_0:", assetId: null, reference: "<Picture 1>" },
      { portId: "9:image_1:", assetId: "asset-character-linlan", reference: "<Picture 2>" },
      { portId: "9:video_0:", assetId: null, reference: "<Video 1>" },
      { portId: "9:audio_0:", assetId: null, reference: "<Audio 1>" },
    ]);
  });

  it("uses whichever prompt tab is selected and shows the source in the bottom action bar", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const task = structuredClone(mockStoryboard.tasks[0]);
    task.aiPrompt = "AI增强后的镜头提示词";
    task.generationParams = { ...task.generationParams, userPrompt: "用户原始提示词", promptSource: "user" };
    task.finalPrompt = "用户原始提示词";
    renderEditor(onSave, vi.fn(), task);

    expect(screen.getByText("当前使用：用户提示词")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /AI 增强/ }));
    expect(screen.getByText("已使用AI增强提示词")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(onSave.mock.calls[0][0]).toMatchObject({
      aiPrompt: "AI增强后的镜头提示词",
      finalPrompt: "AI增强后的镜头提示词",
      generationParams: {
        promptSource: "ai",
        userPrompt: "用户原始提示词",
      },
    });
  });

  it("reopens on the prompt source that was last selected", () => {
    const task = structuredClone(mockStoryboard.tasks[0]);
    task.aiPrompt = "AI增强后的镜头提示词";
    task.finalPrompt = task.aiPrompt;
    task.generationParams = { ...task.generationParams, promptSource: "ai", userPrompt: "用户原始提示词", aiPromptViewMode: "text" };
    renderEditor(vi.fn(), vi.fn(), task);

    expect(screen.getByRole("tab", { name: /AI 增强/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("已使用AI增强提示词")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /文本/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("combobox")).toHaveAttribute("data-value", `legacy-${task.id}`);
  });

  it("cancels without saving", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const onClose = vi.fn();
    renderEditor(onSave, onClose);

    await user.click(screen.getByRole("button", { name: "取消" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
