import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "./App";
import { MockProjectGateway } from "./gateways/mockProjectGateway";
import type { ProjectEvent, ProjectGateway } from "./gateways/projectGateway";
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

describe("ShotMill 项目工作台", () => {
  beforeEach(() => localStorage.clear());
  it("创建工程时要求文件位置，并可从指定文件打开工程", async () => {
    const user = userEvent.setup();
    const gateway = new MockProjectGateway();
    const create = vi.spyOn(gateway, "createProject");
    const open = vi.spyOn(gateway, "openProjectFile");
    render(<OverlayProvider><App gateway={gateway} /></OverlayProvider>);
    await user.click(await screen.findByRole("button", { name: "新建项目" }));
    const createDialog = screen.getByRole("dialog", { name: "新建项目" });
    await user.type(within(createDialog).getByRole("textbox", { name: "项目名称" }), "新工程");
    expect(within(createDialog).getByRole("button", { name: "创建项目" })).toBeDisabled();
    await user.type(within(createDialog).getByRole("textbox", { name: "工程文件位置" }), "G:\\Projects\\film.shotmill");
    await user.click(within(createDialog).getByRole("button", { name: "创建项目" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith({
      title: "新工程", path: "G:\\Projects\\film.shotmill",
    }));
    await user.click(await screen.findByRole("button", { name: "返回项目首页" }));
    await user.click(screen.getByRole("button", { name: "打开工程" }));
    const openDialog = screen.getByRole("dialog", { name: "打开工程" });
    await user.type(within(openDialog).getByRole("textbox", { name: "工程文件位置" }), "G:\\Projects\\film.shotmill");
    await user.click(within(openDialog).getByRole("button", { name: "打开" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith("G:\\Projects\\film.shotmill"));
    await user.click(await screen.findByRole("button", { name: "返回项目首页" }));
    open.mockRejectedValueOnce(new Error("工程文件无法打开"));
    await user.click(screen.getByRole("button", { name: "打开工程" }));
    const failedDialog = screen.getByRole("dialog", { name: "打开工程" });
    await user.type(within(failedDialog).getByRole("textbox", { name: "工程文件位置" }), "G:\\Projects\\missing.shotmill");
    await user.click(within(failedDialog).getByRole("button", { name: "打开" }));
    expect(await within(failedDialog).findByRole("alert")).toHaveTextContent("工程文件无法打开");
  });
  it("coalesces events received during a refresh into a follow-up refresh", async () => {
    const user = userEvent.setup();
    const gateway: ProjectGateway = new MockProjectGateway();
    let notify!: (event: ProjectEvent) => void;
    let projectId = "";
    vi.spyOn(gateway, "subscribeProject").mockImplementation((id, listener) => {
      projectId = id;
      notify = listener;
      return () => undefined;
    });
    render(<OverlayProvider><App gateway={gateway} /></OverlayProvider>);
    await openFirstProject(user);
    await waitFor(() => expect(notify).toBeDefined());
    const original = gateway.getProjectSettings.bind(gateway);
    let release!: () => void;
    const held = new Promise<void>(resolve => { release = resolve; });
    const settings = vi.spyOn(gateway, "getProjectSettings").mockImplementationOnce(async id => {
      await held;
      return original(id);
    });
    act(() => { notify({ type: "task.updated", projectId }); });
    expect(settings).toHaveBeenCalledTimes(1);
    act(() => {
      notify({ type: "job.completed", projectId });
      notify({ type: "task.updated", projectId });
    });
    expect(settings).toHaveBeenCalledTimes(1);
    await act(async () => { release(); });
    await waitFor(() => expect(settings).toHaveBeenCalledTimes(2));
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
  it("项目配置只编辑项目信息，资产在时间线管理", async () => {
    const user = userEvent.setup();
    renderApp();
    await openFirstProject(user);

    await user.click(screen.getByRole("button", { name: "项目配置" }));
    const dialog = screen.getByRole("dialog", { name: "项目配置" });
    expect(within(dialog).getByRole("textbox", { name: "项目标题" })).toBeInTheDocument();
    expect(within(dialog).queryByText("资产管理")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("任务回收站")).not.toBeInTheDocument();
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
