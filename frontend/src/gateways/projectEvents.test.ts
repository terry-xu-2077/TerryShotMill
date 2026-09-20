import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpProjectGateway } from "./projectGateway";

class Source extends EventTarget {
  static instances: Source[] = [];
  close = vi.fn();
  constructor(_url: string) { super(); Source.instances.push(this); }
}
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); Source.instances = []; });

describe("project event recovery", () => {
  it("refreshes on connection and periodically recovers missed terminal events", () => {
    vi.useFakeTimers(); vi.stubGlobal("EventSource", Source);
    const listener = vi.fn();
    const stop = new HttpProjectGateway().subscribeProject("p", listener);
    Source.instances[0].dispatchEvent(new Event("open"));
    expect(listener).toHaveBeenCalledWith({ type: "project.sync_required", projectId: "p" });
    listener.mockClear();
    vi.advanceTimersByTime(30000);
    expect(listener).toHaveBeenCalledTimes(1);
    stop(); listener.mockClear(); vi.advanceTimersByTime(60000);
    expect(listener).not.toHaveBeenCalled();
  });

  it("reconnects after transport failure and cancels retries on navigation", () => {
    vi.useFakeTimers(); vi.stubGlobal("EventSource", Source);
    const stop = new HttpProjectGateway().subscribeProject("p", vi.fn());
    Source.instances[0].dispatchEvent(new Event("error"));
    vi.advanceTimersByTime(3000);
    expect(Source.instances).toHaveLength(2);
    expect(Source.instances[0].close).toHaveBeenCalled();
    Source.instances[1].dispatchEvent(new Event("error"));
    stop(); vi.advanceTimersByTime(3000);
    expect(Source.instances).toHaveLength(2);
  });
});
