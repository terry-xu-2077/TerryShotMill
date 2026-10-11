import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../../App";
import { MockProjectGateway } from "../../gateways/mockProjectGateway";
import { OverlayProvider } from "../../ui/overlay";

it("opens the timeline overview, creates another timeline, and remembers the selected one", async () => {
  const user = userEvent.setup();
  const gateway = new MockProjectGateway();
  render(<OverlayProvider><App gateway={gateway} /></OverlayProvider>);
  await user.click(await screen.findByRole("button", { name: "打开项目 异星边境 初到基地" }));
  await user.click(screen.getByRole("button", { name: "返回时间线列表" }));
  expect(screen.getByRole("button", { name: "新建时间线" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "任务视图" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "新建时间线" }));
  await user.type(screen.getByPlaceholderText("时间线名称"), "第二条时间线");
  await user.click(screen.getByRole("button", { name: "创建" }));
  await waitFor(() => expect(screen.getByRole("heading", { name: "第二条时间线" })).toBeInTheDocument());
  const projects = await gateway.listProjects();
  const settings = await gateway.getProjectSettings(projects[0].id);
  expect(settings.director?.selectedTimelineId).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "返回时间线列表" }));
  await user.click(screen.getByRole("button", { name: "浏览生成结果" }));
  expect(screen.getByRole("heading", { name: "生成结果" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "返回项目首页" }));
  await user.click(await screen.findByRole("button", { name: "打开项目 异星边境 初到基地" }));
  expect(screen.getByRole("heading", { name: "生成结果" })).toBeInTheDocument();
});
