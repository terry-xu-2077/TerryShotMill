import { useEffect, useRef, useState } from "react";
import type { ImportConfigurationGateway, PendingImportConfiguration } from "../../gateways/importConfigurationGateway";
import { Select } from "../../ui/Select";
import { Dialog } from "../../ui/overlay";
import { Button } from "../../ui/primitives";
import "./ImportConfigurationDialog.css";

export function ImportConfigurationDialog({ projectId, gateway, onClose }: {
  projectId: string; gateway: ImportConfigurationGateway; onClose: () => void;
}) {
  const [items, setItems] = useState<PendingImportConfiguration[]>([]);
  const [options, setOptions] = useState<{ value: string; label: string }[]>([]);
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const active = useRef(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(""); setSelected({});
    Promise.all([gateway.pending(projectId), gateway.options()]).then(([pending, choices]) => {
      if (!cancelled) { setItems(pending); setOptions(choices); }
    }).catch(failure => {
      if (!cancelled) setError(failure instanceof Error ? failure.message : "配置加载失败");
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId, gateway, reload]);
  const confirm = async (item: PendingImportConfiguration) => {
    if (active.current || !selected[item.taskId] || error) return;
    active.current = true; setBusy(true);
    try {
      await gateway.confirm(projectId, item.taskId, selected[item.taskId], item.revision);
      setItems(current => current.filter(row => row.taskId !== item.taskId));
    } catch (failure) {
      setError(`${failure instanceof Error ? failure.message : "确认失败"} 请刷新列表核对当前状态。`);
    } finally { active.current = false; setBusy(false); }
  };
  return <Dialog open icon="configure" title="确认生成配置" onClose={() => { if (!active.current) onClose(); }}>
    <div className="import-configuration-dialog" aria-busy={loading || busy}>
      {loading ? <p className="import-configuration-copy" role="status">正在加载…</p>
        : !error && !items.length ? <p className="import-configuration-copy" role="status">没有待确认的任务。</p>
          : !error && !options.length && <p className="import-configuration-copy">本机没有可用工作流，请先在应用设置中配置并启用。</p>}
      {error && <p className="import-configuration-error" role="alert">{error}</p>}
      {!loading && !error && <div className="import-configuration-list" aria-label="待确认任务">
        {items.map(item => <div className="import-configuration-row" key={item.taskId}>
          <div className="import-configuration-heading">
            <strong className="import-configuration-copy">{item.title}</strong>
            {item.sourceConfigurationId && <span className="import-configuration-copy">原配置：{item.sourceConfigurationId}</span>}
          </div>
          <div className="import-configuration-actions">
              <div className="import-configuration-select"><Select ariaLabel={`${item.title}的本机工作流`}
                value={selected[item.taskId] ?? ""} options={[{ value: "", label: "选择本机工作流" }, ...options]}
                disabled={busy || !options.length} onChange={value => setSelected(current => ({ ...current, [item.taskId]: value }))} /></div>
              <Button disabled={busy || !selected[item.taskId]} onClick={() => void confirm(item)}>确认配置</Button>
            </div>
        </div>)}
      </div>}
      <footer className="import-configuration-footer">
        <Button disabled={busy} onClick={onClose}>关闭</Button>
        <Button disabled={busy || loading} onClick={() => setReload(value => value + 1)}>刷新列表</Button>
      </footer>
    </div>
  </Dialog>;
}
