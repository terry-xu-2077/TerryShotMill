import { TextField } from "../../ui/primitives";
import { Select } from "../../ui/Select";
import type { ComfyUIWorkflow, WorkflowNumericBinding } from "../../gateways/projectGateway";

export type NumericBindingDraft = Omit<WorkflowNumericBinding, "value" | "fps" | "frameMultiple" | "frameOffset"> & {
  value: string; fps: string; frameMultiple: string; frameOffset: string;
};

export function numericDraft(bindings: WorkflowNumericBinding[] = []): NumericBindingDraft[] {
  return bindings.map((item) => ({ ...item, value: item.value == null ? "" : String(item.value), fps: String(item.fps ?? 24), frameMultiple: String(item.frameMultiple ?? 1), frameOffset: String(item.frameOffset ?? 0) }));
}

export function serializeNumericBindings(drafts: NumericBindingDraft[]): WorkflowNumericBinding[] | null {
  const result: WorkflowNumericBinding[] = [];
  for (const draft of drafts) {
    const fps = Number(draft.fps), frameMultiple = Number(draft.frameMultiple), frameOffset = Number(draft.frameOffset);
    if (!draft.fps.trim() || !Number.isFinite(fps) || fps <= 0 || fps > 1000 || !draft.frameMultiple.trim() || !Number.isInteger(frameMultiple) || frameMultiple < 1 || frameMultiple > 1024 || !draft.frameOffset.trim() || !Number.isInteger(frameOffset) || frameOffset < 0 || frameOffset >= frameMultiple) return null;
    const value = draft.source === "constant" ? Number(draft.value) : null;
    if (draft.source === "constant" && (!draft.value.trim() || !Number.isFinite(value))) return null;
    result.push({ portId: draft.portId, source: draft.source, value, fps, frameMultiple, frameOffset });
  }
  return result;
}

export function WorkflowNumericBindingsEditor({ workflow, bindings, onChange }: {
  workflow?: ComfyUIWorkflow; bindings: NumericBindingDraft[]; onChange: (bindings: NumericBindingDraft[]) => void;
}) {
  const ports = workflow?.inputs.filter((port) => ["INT", "FLOAT"].includes(port.type)) ?? [];
  const rows = ports.map((port) => ({ id: `${port.targetNodeId ?? ""}:${port.targetPort || port.portName || port.name}:${port.sourceNodeId ?? ""}`, label: `${port.name} · ${port.targetPort || port.portName || port.name}` }));
  bindings.forEach((binding) => { if (!rows.some((row) => row.id === binding.portId)) rows.push({ id: binding.portId, label: "已保存的数值输入 · 请读取工作流核对" }); });
  const update = (portId: string, patch: Partial<NumericBindingDraft>) => {
    const current = bindings.find((item) => item.portId === portId) ?? { portId, source: "constant" as const, value: "", fps: "24", frameMultiple: "1", frameOffset: "0" };
    onChange([...bindings.filter((item) => item.portId !== portId), { ...current, ...patch }]);
  };
  return <section className="workflow-numeric-settings" aria-label="工作流数值控制">
    <strong>时长与数值控制</strong>
    {!rows.length && <p className="workflow-numeric-note">{workflow ? "此工作流未暴露数值输入，视频时长使用工作流默认值。" : "读取并选择工作流后，可配置它的数值输入。"}</p>}
    {rows.map((row) => {
      const binding = bindings.find((item) => item.portId === row.id);
      return <div className="workflow-numeric-row" key={row.id}>
        <label className="application-settings-field"><span>{row.label}</span><Select ariaLabel={`${row.label}来源`} value={binding?.source ?? "default"} onChange={(source) => source === "default" ? onChange(bindings.filter((item) => item.portId !== row.id)) : update(row.id, { source: source as WorkflowNumericBinding["source"] })} options={[
          { value: "default", label: "工作流默认值" }, { value: "durationSeconds", label: "任务总秒数" }, { value: "frameCount", label: "按总秒数换算帧数" }, { value: "constant", label: "固定数值" },
        ]} /></label>
        {binding?.source === "constant" && <label className="application-settings-field"><span>固定数值</span><TextField value={binding.value} onChange={(value) => update(row.id, { value })} /></label>}
        {binding?.source === "frameCount" && <div className="workflow-frame-rule">
          <label className="application-settings-field"><span>每秒帧数</span><TextField value={binding.fps} onChange={(fps) => update(row.id, { fps })} /></label>
          <label className="application-settings-field"><span>帧数倍数</span><TextField value={binding.frameMultiple} onChange={(frameMultiple) => update(row.id, { frameMultiple })} /></label>
          <label className="application-settings-field"><span>帧数偏移</span><TextField value={binding.frameOffset} onChange={(frameOffset) => update(row.id, { frameOffset })} /></label>
          <p className="workflow-numeric-note">向上取满足规则的帧数。例如倍数 4、偏移 1 表示 4n+1；普通帧数用倍数 1、偏移 0。</p>
        </div>}
      </div>;
    })}
  </section>;
}
