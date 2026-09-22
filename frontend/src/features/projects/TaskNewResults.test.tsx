import { act, render, renderHook, screen } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";
import { TaskNewResults, useViewedResults } from "./TaskNewResults";

beforeEach(() => localStorage.clear());
it("shows only actual unread results, independently for video and prompt", () => {
  const { result, unmount } = renderHook(useViewedResults);
  expect(result.current.unread()).toEqual([]);
  expect(result.current.unread({ video: null, prompt: null })).toEqual([]);
  const revisions = { video: "v1", prompt: "p1" };
  expect(result.current.unread(revisions)).toEqual(["video", "prompt"]);
  act(() => result.current.markViewed("video", "v1"));
  expect(result.current.unread(revisions)).toEqual(["prompt"]);
  unmount();
  const restored = renderHook(useViewedResults);
  expect(restored.result.current.unread(revisions)).toEqual(["prompt"]);
  expect(restored.result.current.unread({ video: "v2", prompt: "p1" })).toEqual(["video", "prompt"]);
});
it("renders distinct stickers with only the visible word 新", () => {
  const { rerender, container } = render(<TaskNewResults kinds={[]} />);
  expect(container).toBeEmptyDOMElement();
  rerender(<TaskNewResults kinds={["video", "prompt"]} />);
  expect(screen.getByRole("img", { name: "新视频结果" })).toHaveTextContent(/^新$/);
  expect(screen.getByRole("img", { name: "新提示词增强结果" })).toHaveTextContent(/^新$/);
});
