import { afterEach, expect, it, vi } from "vitest";
import { projectTransferGateway } from "./projectTransferGateway";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.resetModules();
});

it("uses an encoded native download URL without buffering the ZIP", () => {
  const request = vi.fn();
  vi.stubGlobal("fetch", request);
  expect(projectTransferGateway.exportUrl("p/one")).toBe("/api/v1/projects/p%2Fone/export");
  expect(request).not.toHaveBeenCalled();
});

it("prepares and discards a download without fetching its bytes", async () => {
  const request = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ token: "t", expiresInSeconds: 300 })))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", request);
  expect(await projectTransferGateway.prepareExport("p/one")).toEqual({ token: "t", expiresInSeconds: 300 });
  expect(request).toHaveBeenNthCalledWith(1, "/api/v1/projects/p%2Fone/exports", { method: "POST" });
  expect(projectTransferGateway.downloadUrl("t/one")).toBe("/api/v1/projects/exports/t%2Fone");
  await projectTransferGateway.discardExport("t");
  expect(request).toHaveBeenNthCalledWith(2, "/api/v1/projects/exports/t", { method: "DELETE" });
});

it("uploads the original file with a browser-owned multipart boundary", async () => {
  const outcome = { projectId: "new-project", providerRequirements: [
    { kind: "video", requiresConfiguration: true, workflowId: "video.json" },
  ] };
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify(outcome)));
  vi.stubGlobal("fetch", request);
  const file = new File(["zip"], "项目.zip", { type: "application/zip" });
  const abort = new AbortController();
  expect(await projectTransferGateway.importPackage(file, abort.signal)).toEqual(outcome);
  const [url, init] = request.mock.calls[0];
  expect(url).toBe("/api/v1/projects/import");
  expect(init.method).toBe("POST");
  expect(init.body.get("file")).toBe(file);
  expect(init.headers).toBeUndefined();
  expect(init.signal).toBe(abort.signal);
});

it("preserves backend failure messages and never automatically retries an import", async () => {
  const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: {
    code: "PROJECT_PACKAGE_INVALID", message: "项目包损坏或格式不受支持。",
  } }), { status: 422 }));
  vi.stubGlobal("fetch", request);
  await expect(projectTransferGateway.importPackage(new File(["bad"], "bad.zip")))
    .rejects.toMatchObject({ code: "PROJECT_PACKAGE_INVALID", message: "项目包损坏或格式不受支持。" });
  expect(request).toHaveBeenCalledTimes(1);
});

it("respects a configured remote API base for native downloads", async () => {
  vi.stubEnv("VITE_SHOTMILL_API_BASE_URL", "http://desktop:8000/api/v1/");
  vi.resetModules();
  const { projectTransferGateway: remote } = await import("./projectTransferGateway");
  expect(remote.exportUrl("project")).toBe("http://desktop:8000/api/v1/projects/project/export");
});
