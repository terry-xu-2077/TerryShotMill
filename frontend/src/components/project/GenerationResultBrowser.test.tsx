import { fireEvent, render, screen } from "@testing-library/react";
import { makeMockProjects } from "../../mock/projects";
import { GenerationResultBrowser } from "./GenerationResultBrowser";

it("shows every saved video version and opens the chosen result", () => {
  const project = makeMockProjects()[0];
  const onPlay = vi.fn();
  render(<GenerationResultBrowser project={project} onPlay={onPlay} />);
  const available = project.snapshot.results.filter(result => result.videoUrl);
  expect(screen.getAllByRole("button", { name: /^播放结果/ })).toHaveLength(available.length);
  fireEvent.click(screen.getByRole("button", { name: /版本 2/ }));
  expect(onPlay).toHaveBeenCalledWith(available[1], expect.objectContaining({ title: "特瑞在荒漠驰骋" }));
});
