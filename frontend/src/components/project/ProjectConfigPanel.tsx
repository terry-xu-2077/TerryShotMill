import { useEffect, useRef, useState } from "react";
import { Button, Checkbox, TextField } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";
import type { ProjectCoverSelection } from "../../gateways/projectGateway";
import type { DirectorProject } from "./projectTypes";
import { ProjectCoverEditor } from "./ProjectCoverEditor";

type ProjectSettingsPatch = Pick<DirectorProject, "title" | "description" | "useDescriptionForAiPrompt"> & { cover?: ProjectCoverSelection };

export function ProjectConfigPanel({ open, project, onClose, onSave }: {
  open: boolean;
  project: DirectorProject;
  onClose: () => void;
  onSave: (settings: ProjectSettingsPatch) => void | Promise<void>;
}) {
  const [title, setTitle] = useState(project.title);
  const [description, setDescription] = useState(project.description);
  const [useDescriptionForAiPrompt, setUseDescriptionForAiPrompt] = useState(project.useDescriptionForAiPrompt);
  const [cover, setCover] = useState<ProjectCoverSelection>();
  const [coverPreview, setCoverPreview] = useState<string>();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const savePending = useRef(false);
  const editSession = useRef<string | null>(null);

  useEffect(() => {
    if (!open) { editSession.current = null; return; }
    if (editSession.current === project.id) return;
    editSession.current = project.id;
    setTitle(project.title);
    setDescription(project.description);
    setUseDescriptionForAiPrompt(project.useDescriptionForAiPrompt);
    setCover(undefined);
    setCoverPreview(undefined);
    setSaveError("");
  }, [open, project]);

  const close = () => { if (!savePending.current) onClose(); };
  const save = async () => {
    if (savePending.current || !title.trim()) return;
    savePending.current = true;
    setSaving(true);
    setSaveError("");
    try {
      await onSave({ title: title.trim(), description: description.trim(), useDescriptionForAiPrompt,
        ...(cover ? { cover } : {}) });
      onClose();
    } catch {
      setSaveError("保存失败，修改已保留，请检查连接后重试。");
    } finally {
      savePending.current = false;
      setSaving(false);
    }
  };

  return <Dialog open={open} size="wide" icon="configure" title="项目配置" onClose={close}>
    <div className="project-config-dialog project-config-dialog-v2">
      <section className="project-config-content" inert={saving}>
        <div className="project-config-info">
          <ProjectCoverEditor assets={project.snapshot.assets} results={project.snapshot.results}
            coverUrl={project.coverUrl} automaticCoverUrl={project.automaticCoverUrl}
            previewUrl={coverPreview} custom={Boolean(project.coverAssetId)} value={cover}
            onChange={(selection, preview) => { setCover(selection); setCoverPreview(preview); }} />
          <label><span>项目标题</span><TextField value={title} onChange={setTitle} /></label>
          <label><span>项目简介</span><textarea value={description}
            onChange={event => setDescription(event.target.value)} rows={8}
            placeholder="用几句话说明项目的世界观、题材、角色关系或视觉基调。" /></label>
          <div className="project-context-checkbox">
            <Checkbox checked={useDescriptionForAiPrompt} onChange={setUseDescriptionForAiPrompt}
              ariaLabel="AI 增强时使用项目简介作为背景" />
            <span><strong>AI 增强时使用项目简介作为背景</strong></span>
          </div>
        </div>
      </section>
      <footer className="project-config-actions">
        {saveError && <span className="project-config-save-error" role="alert">{saveError}</span>}
        <Button disabled={saving} onClick={close}>取消</Button>
        <Button variant="accent" disabled={saving || !title.trim()} onClick={() => void save()}>{saving ? "保存中…" : "保存"}</Button>
      </footer>
    </div>
  </Dialog>;
}
