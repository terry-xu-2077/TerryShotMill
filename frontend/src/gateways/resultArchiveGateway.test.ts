import { afterEach, expect, it, vi } from "vitest";
import { resultArchiveGateway } from "./resultArchiveGateway";

afterEach(() => vi.unstubAllGlobals());

it("deletes only the encoded archive identity and accepts an empty response", async () => {
  const request = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", request);
  await expect(resultArchiveGateway.delete("archive/one")).resolves.toBeUndefined();
  expect(request).toHaveBeenCalledExactlyOnceWith(
    "/api/v1/result-archive/archive%2Fone", { method: "DELETE" },
  );
});

it("surfaces deletion failure without automatic destructive retries", async () => {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    error: { code: "ARCHIVE_NOT_FOUND", message: "归档结果不存在" },
  }), { status: 404 }));
  vi.stubGlobal("fetch", request);
  await expect(resultArchiveGateway.delete("missing")).rejects.toMatchObject({
    code: "ARCHIVE_NOT_FOUND", message: "归档结果不存在",
  });
  expect(request).toHaveBeenCalledTimes(1);
});
