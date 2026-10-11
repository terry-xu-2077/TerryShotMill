import { useRef, useState } from "react";
import { ProjectGatewayError } from "../../gateways/projectGateway";
import type { ProjectImportOutcome, ProjectTransferGateway } from "../../gateways/projectTransferGateway";
import { Dialog } from "../../ui/overlay";
import { Button } from "../../ui/primitives";
import "./ProjectImportDialog.css";

export function ProjectImportDialog({ gateway, onChanged, onClose, onBrowsePath }: {
  gateway: Pick<ProjectTransferGateway, "importPackage" | "exportUrl">;
  onChanged: () => Promise<void>;
  onClose: () => void;
  onBrowsePath?: () => Promise<string | null>;
}) {
  const active = useRef(false);
  const [file, setFile] = useState<File>();
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<ProjectImportOutcome>();
  const [refreshed, setRefreshed] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState("");
  const close = () => { if (!active.current) onClose(); };

  const submit = async () => {
    if (active.current || uncertain || (!outcome && (!file || !path.trim()))) return;
    active.current = true;
    setBusy(true);
    setError("");
    let committed = outcome;
    try {
      if (!committed) {
        committed = await gateway.importPackage(file!, path.trim());
        setOutcome(committed);
      }
      await onChanged();
      setRefreshed(true);
    } catch (failure) {
      const message = failure instanceof Error ? failure.message : "操作失败";
      if (committed) {
        setError(`项目已导入，列表刷新失败：${message}`);
      } else if (failure instanceof ProjectGatewayError && failure.status >= 400 && failure.status < 500) {
        setError(message);
      } else {
        setUncertain(true);
        setError("未能确认导入结果，请关闭后刷新项目列表，核对是否已导入，避免重复创建项目。");
      }
    } finally {
      active.current = false;
      setBusy(false);
    }
  };

  return <Dialog open icon="create" title="导入项目" onClose={close}>
    <div className="project-import-dialog" aria-busy={busy}>
      {!outcome && <label className="project-import-file">
        <span>项目 ZIP 包</span>
        <input className="project-import-input" type="file" accept=".zip,application/zip"
          disabled={busy || uncertain} onChange={event => {
            setFile(event.target.files?.[0]);
            setError("");
          }} />
      </label>}
      {!outcome && <div className="project-import-file">
        <label htmlFor="import-project-path">导入后的工程文件位置</label>
        <div className="project-import-path-row">
          <input id="import-project-path" value={path} disabled={busy || uncertain}
            onChange={event => setPath(event.target.value)} placeholder="选择目录并填写 .shotmill 文件名" />
          {onBrowsePath && <Button disabled={busy || uncertain} onClick={() => void onBrowsePath().then(value => {
            if (value) setPath(value);
          })}>浏览…</Button>}
        </div>
      </div>}
      <div className="project-import-status" role="status" aria-live="polite">
        {busy ? (outcome ? "正在刷新项目列表…" : "正在上传并导入项目…")
          : outcome ? "项目已导入" : "项目和媒体将解包到指定位置，不覆盖已有文件。"}
      </div>
      {outcome && <p className="project-import-notice">
        工作流和模型配置未随项目迁移。导入任务生成前，请在“项目管理 → 确认生成配置”中选择本机工作流。
      </p>}
      {error && <p className="project-import-error" role="alert">{error}</p>}
      <footer className="project-import-actions">
        <Button disabled={busy} onClick={close}>{outcome || uncertain ? "关闭" : "取消"}</Button>
        {!refreshed && !uncertain && <Button variant="accent" disabled={busy || (!outcome && (!file || !path.trim()))}
          onClick={() => void submit()}>{outcome ? "重试刷新" : "导入"}</Button>}
      </footer>
    </div>
  </Dialog>;
}
