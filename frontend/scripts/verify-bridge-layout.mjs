import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium } from "@playwright/test";

// Uses an isolated browser and graph; never queues or saves a user workflow.
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto(process.env.COMFYUI_URL || "http://127.0.0.1:8188");
  await page.waitForFunction(() => window.LiteGraph?.registered_node_types?.ShotMillIOBridgeIn);
  const result = await page.evaluate(async () => {
    const { app } = await import("/scripts/app.js");
    const settle = () => new Promise((resolve) => requestAnimationFrame(() => queueMicrotask(resolve)));
    const graph = new LGraph();
    const bridge = LiteGraph.createNode("ShotMillIOBridgeIn");
    graph.add(bridge);
    bridge.pos = [460, 170];
    await settle();
    for (let index = 0; index < 12; index++) {
      const source = LiteGraph.createNode("LoadImage");
      graph.add(source);
      source.pos = [80, 100 + index * 40];
      source.flags.collapsed = true;
      source.connect(0, bridge, index);
      await settle();
      const target = LiteGraph.createNode("ShotMillIOBridgeOut");
      graph.add(target);
      target.pos = [850, 100 + index * 40];
      target.flags.collapsed = true;
      bridge.connect(index, target, 0);
    }
    const snapshot = (node) => ({
      height: node.size[1],
      computedHeight: node.computeSize()[1],
      inputs: node.inputs.length,
      outputs: node.outputs.length,
      inputLinks: node.inputs.map((slot) => slot.link),
      outputLinks: node.outputs.map((slot) => slot.links ?? []),
    });
    const connected = snapshot(bridge);
    const workflow = graph.serialize();
    const saved = workflow.nodes.find((node) => String(node.id) === String(bridge.id));
    saved.size = [260, 5200];
    app.graph.configure(workflow);
    await settle();
    const restored = app.graph.getNodeById(bridge.id);
    const reloaded = snapshot(restored);
    restored.disconnectInput(11);
    await settle();
    const disconnected = snapshot(restored);
    const sourceId = workflow.nodes.find((node) => node.type === "LoadImage" && node.pos[1] === 540).id;
    app.graph.getNodeById(sourceId).connect(0, restored, 11);
    await settle();
    const reconnected = snapshot(restored);
    app.canvas.ds.scale = 1;
    app.canvas.ds.offset = [0, 0];
    app.canvas.setDirty(true, true);
    await settle();
    return { connected, reloaded, disconnected, reconnected };
  });
  for (const state of Object.values(result)) {
    assert.equal(state.height, state.computedHeight);
    assert.ok(state.height < 400, `Unexpected node height: ${state.height}`);
    assert.equal(state.inputs, state.outputs);
  }
  assert.equal(result.connected.inputs, 13);
  assert.deepEqual(result.reloaded.inputLinks, result.connected.inputLinks);
  assert.deepEqual(result.reloaded.outputLinks, result.connected.outputLinks);
  assert.equal(result.reconnected.inputs, 13);
  assert.deepEqual(result.reconnected.outputLinks, result.connected.outputLinks);
  await mkdir("../.artifacts/bridge-layout", { recursive: true });
  await page.screenshot({ path: "../.artifacts/bridge-layout/bridge-in.png" });
  console.log(JSON.stringify(result, null, 2));
} finally {
  await browser.close();
}
