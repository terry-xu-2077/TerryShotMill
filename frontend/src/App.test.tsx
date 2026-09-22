import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "./App";
import { MockProjectGateway } from "./gateways/mockProjectGateway";
import { OverlayProvider } from "./ui/overlay";

function renderApp() {
  return render(
    <OverlayProvider>
      <App gateway={new MockProjectGateway()} />
    </OverlayProvider>,
  );
}

async function openFirstProject(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "打开项目 异星边境 初到基地" }));
}

describe("V0.6 Terry导演工作台", () => {
  beforeEach(() => localStorage.clear());
  it("selects tasks with Ctrl+A and keeps text selection native inside the editor", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);
    const shortcut = new KeyboardEvent("keydown", { key: "a", ctrlKey: true, bubbles: true, cancelable: true });
    fireEvent(window, shortcut);
    expect(shortcut.defaultPrevented).toBe(true);
    const checks = screen.getAllByRole("checkbox", { name: /^选择任务/ });
    checks.forEach(check => expect(check).toBeChecked());
    const toolbar = screen.getByRole("region", { name: "任务操作" });
    expect(within(toolbar).getByRole("button", { name: "增强提示词" })).toBeVisible();
    await user.click(within(toolbar).getByRole("button", { name: "取消选择" }));
    checks.forEach(check => expect(check).not.toBeChecked());
    expect(screen.queryByRole("region", { name: "任务操作" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "新建任务卡" }));
    const input = screen.getAllByRole("textbox")[0];
    const textShortcut = new KeyboardEvent("keydown", { key: "a", ctrlKey: true, bubbles: true, cancelable: true });
    fireEvent(input, textShortcut);
    expect(textShortcut.defaultPrevented).toBe(false);
  });
  it("opens video directly from task thumbnails in both collection views", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);
    for (const mode of ["list", "card"]) {
      if (mode === "card") await user.click(screen.getByRole("button", { name: "切换为卡片视图" }));
      await user.click(screen.getByRole("button", { name: "播放视频 · 特瑞在荒漠驰骋" }));
      const dialog = screen.getByRole("dialog", { name: "播放结果 · 特瑞在荒漠驰骋" });
      expect(dialog.querySelector("video")?.autoplay).toBe(true);
      expect(screen.queryByTestId("simple-task-editor")).not.toBeInTheDocument();
      await user.click(within(dialog).getByRole("button", { name: "关闭" }));
    }
  });
  it("默认打开项目首页，只负责选择或新建项目", async () => {
    renderApp();

    expect(screen.getByRole("main", { name: "项目首页" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Terry导演工作台" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "打开项目 异星边境 初到基地" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开项目 诡道异仙 第一部" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开项目 重生之我是高中学霸" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建项目" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "主导航" })).not.toBeInTheDocument();
  });

  it("进入项目后默认是列表模式，并以任务行形式提供新建入口", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);

    expect(screen.getByRole("main", { name: "项目工作台" })).toBeInTheDocument();
    expect(screen.getAllByText("异星边境 初到基地").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "切换为卡片视图" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "新建任务卡" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^新建任务$/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "返回项目首页" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "项目配置" })).toBeInTheDocument();
    expect(screen.getByText("#1 特瑞在荒漠驰骋")).toBeInTheDocument();
    expect(screen.getByText("#2 越过断层台地")).toBeInTheDocument();
    expect(screen.getByText("#3 驶入临时基地")).toBeInTheDocument();
  });

  it("单击任务只更新右侧只读信息栏，不进入编辑", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);

    await user.click(screen.getByText("#2 越过断层台地").closest("button")!);

    const info = screen.getByRole("complementary", { name: "任务信息" });
    expect(within(info).getByText("任务名：越过断层台地")).toBeInTheDocument();
    expect(within(info).getByRole("heading", { name: "提示词" })).toBeInTheDocument();
    expect(within(info).getByText("生成参数")).toBeInTheDocument();
    expect(within(info).queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("右侧已有生成结果的预览可以点击打开播放窗口", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);
    await user.click(screen.getByRole("button", { name: /^#1 特瑞在荒漠驰骋/ }));

    await user.click(await screen.findByRole("button", { name: "播放任务 特瑞在荒漠驰骋 的生成结果" }));
    const dialog = screen.getByRole("dialog", { name: /播放结果 · 特瑞在荒漠驰骋/ });
    expect(within(dialog).getByRole("button", { name: "关闭" })).toBeInTheDocument();
    expect(dialog.querySelector("video")).not.toBeNull();
  });

  it("双击或右键任务进入同一套悬浮编辑窗", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);

    const firstRow = screen.getByText("#1 特瑞在荒漠驰骋").closest("button")!;
    await user.dblClick(firstRow);
    expect(screen.getByRole("dialog", { name: /特瑞在荒漠驰骋/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "取消" }));

    const secondRow = screen.getByText("#2 越过断层台地").closest("button")!;
    fireEvent.contextMenu(secondRow);
    fireEvent.click(screen.getByRole("menuitem", { name: "查看任务" }));
    expect(await screen.findByRole("dialog", { name: /越过断层台地/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存" })).not.toBeInTheDocument();
    expect(screen.getByText("排队或生成中 · 只读")).toBeInTheDocument();
  });

  it("任务名称可以在编辑窗顶部原位修改并保存", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);

    const firstRow = screen.getByText("#1 特瑞在荒漠驰骋").closest("button")!;
    await user.dblClick(firstRow);
    await user.click(screen.getByTitle("编辑任务名称"));
    const titleInput = screen.getByRole("textbox", { name: "任务名称" });
    await user.clear(titleInput);
    await user.type(titleInput, "特瑞冲入基地");
    await user.keyboard("{Enter}");
    await user.click(screen.getByRole("button", { name: "保存" }));

    expect(await screen.findByText("#1 特瑞冲入基地")).toBeInTheDocument();
  });

  it("列表和卡片是同一任务集合的两种视图，并统一使用内容区新建任务卡", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);

    await user.click(screen.getByRole("button", { name: /卡片/ }));

    expect(screen.getByRole("button", { name: "切换为表格视图" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "新建任务卡" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^新建任务$/ })).not.toBeInTheDocument();
    expect(screen.getByText("#1 特瑞在荒漠驰骋")).toBeInTheDocument();
    expect(screen.getByText("#2 越过断层台地")).toBeInTheDocument();
    expect(screen.getByText("#3 驶入临时基地")).toBeInTheDocument();
  });

  it("首页导航旁打开项目配置，标题只展示，视图切换归属任务区", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);

    const config = screen.getByRole("button", { name: "项目配置" });
    expect(config.closest(".workspace-navigation")).not.toBeNull();
    expect(document.querySelector(".workspace-project-title button")).toBeNull();
    expect(screen.queryByRole("button", { name: "重命名项目" })).not.toBeInTheDocument();
    const area = screen.getByRole("region", { name: "任务区域" });
    const cards = within(area).getByRole("button", { name: "切换为卡片视图" });
    expect(cards.textContent).toBe("");
    expect(screen.getByRole("button", { name: "暗色" }).closest(".project-workspace-topbar")).not.toBeNull();
    await user.click(screen.getByText("#2 越过断层台地").closest("button")!);
    await user.click(cards);
    expect(screen.getByText("#2 越过断层台地").closest("button")).toHaveClass("is-selected");
    await user.click(config);
    expect(screen.getByRole("dialog", { name: "项目配置" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "重命名项目" })).not.toBeInTheDocument();
  });

  it("项目配置可以修改项目标题、简介和 AI 项目背景开关", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);

    await user.click(screen.getByRole("button", { name: "项目配置" }));
    const dialog = screen.getByRole("dialog", { name: "项目配置" });
    const title = within(dialog).getByRole("textbox", { name: /项目标题/ });
    const description = within(dialog).getByRole("textbox", { name: /项目简介/ });
    const background = within(dialog).getByRole("checkbox", { name: /AI 增强时使用项目简介作为背景/ });

    expect(background).toBeChecked();
    await user.clear(title);
    await user.type(title, "异星边境 第二版");
    await user.clear(description);
    await user.type(description, "新的项目背景信息");
    background.focus();
    await user.keyboard(" ");
    expect(background).not.toBeChecked();
    await user.click(within(dialog).getByRole("button", { name: "保存" }));

    expect((await screen.findAllByText("异星边境 第二版")).length).toBeGreaterThan(0);
  });

  it("项目配置包含资产管理入口", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);

    await user.click(screen.getByRole("button", { name: "项目配置" }));
    const dialog = screen.getByRole("dialog", { name: "项目配置" });
    await user.click(within(dialog).getByRole("button", { name: /资产管理/ }));
    expect(within(dialog).getByText("项目资产")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /添加资产/ })).toBeInTheDocument();
  });

  it("列表模式的新建任务卡直接打开任务编辑弹窗", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);

    await user.click(screen.getByRole("button", { name: "新建任务卡" }));

    const dialog = screen.getByRole("dialog", { name: /新任务/ });
    expect(within(dialog).getByRole("button", { name: "生成参数" })).toHaveAttribute("aria-expanded", "false");
    await user.click(within(dialog).getByRole("button", { name: "生成参数" }));
    expect(within(dialog).getByRole("complementary", { name: "任务配置" })).toBeInTheDocument();
    expect(within(dialog).getByRole("region", { name: "提示词编辑" })).toBeInTheDocument();
    expect(within(dialog).getByRole("textbox", { name: "用户提示词可视化" }).textContent).toBe("");
    expect(within(dialog).queryByText("等待填写提示词。")).not.toBeInTheDocument();
    expect(within(dialog).getByRole("tab", { name: "尾帧承接" })).toHaveAttribute("aria-selected", "true");
    expect(within(dialog).getByRole("button", { name: "取消" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "保存" })).toBeInTheDocument();
  });

  it("底部只显示应用设置入口和当前运行摘要", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);

    expect(screen.getByRole("button", { name: /设置/ })).toBeInTheDocument();
    expect(await screen.findByText(/执行中 \d+ 项 · 排队 \d+ 项/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "生成" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "素材" })).not.toBeInTheDocument();
  });

  it("点击返回首页按钮回到项目首页", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);

    await user.click(screen.getByRole("button", { name: "返回项目首页" }));
    expect(screen.getByRole("main", { name: "项目首页" })).toBeInTheDocument();
  });
});
