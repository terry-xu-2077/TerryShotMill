import { afterEach, expect, it, vi } from "vitest";
import { lifecycleGateway } from "./lifecycleGateway";

afterEach(() => vi.unstubAllGlobals());

it("encodes project identity and carries explicit permanent-delete choices", async () => {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ deletedIds: ["t"] })));
  vi.stubGlobal("fetch", request);
  await lifecycleGateway.purgeTasks("p/one", ["t"], false);
  expect(request).toHaveBeenCalledWith("/api/v1/projects/p%2Fone/tasks/permanent-delete", expect.objectContaining({
    method: "POST", body: JSON.stringify({ taskIds: ["t"], archiveResults: false, confirmed: true }),
  }));
});

it("uses backend lifecycle scopes instead of filtering the active list", async () => {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] })));
  vi.stubGlobal("fetch", request);
  await lifecycleGateway.listProjects("trash");
  expect(request).toHaveBeenCalledWith("/api/v1/projects?scope=trash", undefined);
});
