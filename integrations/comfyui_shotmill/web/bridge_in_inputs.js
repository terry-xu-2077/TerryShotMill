import { app } from "../../scripts/app.js";

const BRIDGE_IN_TYPE = "ShotMillIOBridgeIn";
const EMPTY_TYPE = "*";

function nodeType(node) {
  return String(node?.comfyClass || node?.type || node?.constructor?.comfyClass || "");
}

function isBridgeIn(node) {
  return nodeType(node) === BRIDGE_IN_TYPE;
}

function inputName(index) {
  return index === 0 ? "*" : `* ${index + 1}`;
}

function outputName(index) {
  return inputName(index);
}

function syncOutputs(node) {
  if (!isBridgeIn(node) || !Array.isArray(node.inputs)) return;
  if (!Array.isArray(node.outputs)) node.outputs = [];

  const desiredLength = Math.max(1, node.inputs.length);
  while (node.outputs.length < desiredLength) {
    const index = node.outputs.length;
    node.addOutput?.(outputName(index), EMPTY_TYPE);
  }
  while (node.outputs.length > desiredLength && node.outputs.length > 1) {
    const last = node.outputs[node.outputs.length - 1];
    if (Array.isArray(last?.links) && last.links.length > 0) break;
    node.removeOutput?.(node.outputs.length - 1);
  }

  node.outputs.forEach((output, index) => {
    if (!output) return;
    output.name = outputName(index);
    output.label = outputName(index);
    output.type = EMPTY_TYPE;
  });
}

function normalizeInputSlots(node) {
  if (!isBridgeIn(node) || !Array.isArray(node.inputs)) return;

  let lastConnected = -1;
  node.inputs.forEach((input, index) => {
    if (input?.link != null) lastConnected = index;
  });

  const desiredLength = Math.max(1, lastConnected + 2);
  while (node.inputs.length < desiredLength) {
    const index = node.inputs.length;
    const input = node.addInput?.(inputName(index), EMPTY_TYPE);
    if (input) input.rawLink = true;
  }
  while (node.inputs.length > desiredLength && node.inputs.length > 1) {
    const last = node.inputs[node.inputs.length - 1];
    if (last?.link != null) break;
    node.removeInput?.(node.inputs.length - 1);
  }

  node.inputs.forEach((input, index) => {
    if (!input) return;
    input.name = inputName(index);
    input.label = inputName(index);
    input.type = EMPTY_TYPE;
    input.rawLink = true;
  });
  syncOutputs(node);
  const size = node.computeSize?.();
  if (Array.isArray(size) && size.length >= 2) node.setSize?.(size);
  node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: "ShotMill.BridgeInInputs",

  beforeRegisterNodeDef(nodeTypeClass, nodeData) {
    if (nodeData?.name !== BRIDGE_IN_TYPE) return;

    const originalCreated = nodeTypeClass.prototype.onNodeCreated;
    nodeTypeClass.prototype.onNodeCreated = function () {
      const result = originalCreated?.apply(this, arguments);
      queueMicrotask(() => normalizeInputSlots(this));
      return result;
    };

    const originalConfigured = nodeTypeClass.prototype.onConfigure;
    nodeTypeClass.prototype.onConfigure = function () {
      const result = originalConfigured?.apply(this, arguments);
      queueMicrotask(() => normalizeInputSlots(this));
      return result;
    };

    const originalConnections = nodeTypeClass.prototype.onConnectionsChange;
    nodeTypeClass.prototype.onConnectionsChange = function (type, index) {
      const result = originalConnections?.apply(this, arguments);
      if (type === LiteGraph.INPUT) queueMicrotask(() => normalizeInputSlots(this));
      return result;
    };
  },
});
