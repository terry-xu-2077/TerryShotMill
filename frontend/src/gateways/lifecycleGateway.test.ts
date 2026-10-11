import { afterEach, expect, it, vi } from "vitest";
import { lifecycleGateway } from "./lifecycleGateway";

afterEach(() => vi.unstubAllGlobals());

it("encodes project identity for direct task deletion", async () => {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ deletedIds: ["t"] })));
  vi.stubGlobal("fetch", request);
  await lifecycleGateway.deleteTasks("p/one", ["t"]);
  expect(request).toHaveBeenCalledWith("/api/v1/projects/p%2Fone/tasks/delete", expect.objectContaining({
    method: "POST", body: JSON.stringify({ taskIds: ["t"] }),
  }));
});

it("loads current projects without archive or trash scopes", async () => {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] })));
  vi.stubGlobal("fetch", request);
  await lifecycleGateway.listProjects();
  expect(request).toHaveBeenCalledWith("/api/v1/projects", undefined);
});
