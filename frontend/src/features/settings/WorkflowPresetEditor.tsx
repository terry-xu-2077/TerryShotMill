import { useState } from "react";
import { Button, Select, TextField } from "terry-react-ui-library";
import type { ComfyUIWorkflow, ComfyUIWorkflowProfile } from "../../gateways/projectGateway";
import { numericDraft, serializeNumericBindings, WorkflowNumericBindingsEditor, type NumericBindingDraft } from "./WorkflowNumericBindingsEditor";

export function WorkflowPresetEditor({ profiles, workflows, busy, onSave, onRemove }: {
  profiles: ComfyUIWorkflowProfile[]; workflows: ComfyUIWorkflow[]; busy: boolean;
  onSave: (profile: ComfyUIWorkflowProfile) => Promise<boolean>;
  onRemove: (id: string) => void;
}) {
  const [id, setId] = useState("");
  const [workflowFile, setWorkflowFile] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [numericBindings, setNumericBindings] = useState<NumericBindingDraft[]>([]);
  const serializedBindings = serializeNumericBindings(numericBindings);
  const [pending, setPending] = useState(false);
  const edit = (profile?: ComfyUIWorkflowProfile) => {
    setId(profile?.id ?? ""); setWorkflowFile(profile?.workflowFile ?? "");
    setName(profile?.name ?? ""); setDescription(profile?.description ?? "");
    setNumericBindings(numericDraft(profile?.numericBindings));
  };
  const save = async () => {
    if (!name.trim() || !workflowFile || pending || busy || !serializedBindings) return;
    setPending(true);
    try {
      const previous = profiles.find((profile) => profile.id === id);
      const profile = { resolution: "", quality: "", enabled: true, ...previous,
        id: id || `profile-${crypto.randomUUID()}`, name: name.trim(), description: description.trim(), workflowFile, numericBindings: serializedBindings };
      if (await onSave(profile)) setId(profile.id);
    } finally { setPending(false); }
  };
  const choices = workflows.filter((workflow) => workflow.executable && workflow.hasShotmillBridge);
  return <div className="workflow-preset-editor">
    <div className="application-settings-profile-header"><strong>档位预设</strong><Button disabled={busy || pending} onClick={() => edit()}>新建档位</Button></div>
    {profiles.length > 0 && <div className="workflow-preset-list" aria-label="已保存档位">{profiles.map((profile) => <div className="workflow-preset-row" key={profile.id}>
      <button type="button" className="workflow-preset-choice" aria-pressed={id === profile.id} onClick={() => edit(profile)}><strong>{profile.name}</strong><span>{profile.description || profile.workflowFile}</span></button>
      <Button disabled={busy || pending} onClick={() => { onRemove(profile.id); if (id === profile.id) edit(); }} aria-label={`删除档位 ${profile.name}`}>删除</Button>
    </div>)}</div>}
    <div className="workflow-preset-form" inert={busy || pending}>
      <label className="application-settings-field"><span>工作流</span><Select ariaLabel="预设工作流" value={workflowFile} onChange={(file) => { setWorkflowFile(file); setNumericBindings([]); }} options={[
        { value: "", label: "选择工作流" },
        ...(workflowFile && !choices.some((item) => item.relativePath === workflowFile) ? [{ value: workflowFile, label: `${workflowFile} · 尚未读取` }] : []),
        ...choices.map((item) => ({ value: item.relativePath, label: item.name })),
      ]} /></label>
      <label className="application-settings-field"><span>档位名称</span><TextField value={name} onChange={setName} placeholder="例如：人物对白" /></label>
      <label className="application-settings-field"><span>档位简介</span><textarea className="workflow-preset-description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="适用场景和画面特点" rows={3} /></label>
      <WorkflowNumericBindingsEditor workflow={workflows.find((item) => item.relativePath === workflowFile)} bindings={numericBindings} onChange={setNumericBindings} />
      {!serializedBindings && <p className="application-settings-error" role="alert">请填写有效数值；帧率必须大于 0，帧数偏移应小于倍数。</p>}
    </div>
    <div className="workflow-preset-save"><Button variant="accent" disabled={!workflowFile || !name.trim() || busy || pending || !serializedBindings} onClick={() => void save()}>{pending ? "保存中…" : "保存档位预设"}</Button></div>
  </div>;
}
