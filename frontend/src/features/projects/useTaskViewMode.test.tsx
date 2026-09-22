import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useTaskViewMode } from "./useTaskViewMode";

afterEach(() => { localStorage.clear(); vi.restoreAllMocks(); });
it("remembers each project's view across switching and remounting", () => {
  const hook = renderHook(({ id }) => useTaskViewMode(id), { initialProps: { id: "a" } });
  expect(hook.result.current[0]).toBe("list");
  act(() => hook.result.current[1]("card"));
  hook.rerender({ id: "b" });
  expect(hook.result.current[0]).toBe("list");
  hook.rerender({ id: "a" });
  expect(hook.result.current[0]).toBe("card");
  hook.unmount();
  expect(renderHook(() => useTaskViewMode("a")).result.current[0]).toBe("card");
});
it("keeps switching usable when storage is unavailable", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw Error(); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw Error(); });
  const { result } = renderHook(() => useTaskViewMode("a"));
  act(() => result.current[1]("card"));
  expect(result.current[0]).toBe("card");
});
