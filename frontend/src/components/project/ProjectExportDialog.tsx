import { useEffect, useRef, useState } from "react";
import type { ProjectTransferGateway } from "../../gateways/projectTransferGateway";
import { Dialog } from "../../ui/overlay";
import { Button } from "../../ui/primitives";
import "./ProjectExportDialog.css";

export function ProjectExportDialog({ project, gateway, onClose }: {
  project: { id: string; title: string };
  gateway: Pick<ProjectTransferGateway, "prepareExport" | "downloadUrl" | "discardExport">;
  onClose: () => void;
}) {
  const active = useRef(false);
  const unclaimed = useRef<string | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [ticket, setTicket] = useState<{ token: string; expiresInSeconds: number }>();
  const [requested, setRequested] = useState(false);
  const [expired, setExpired] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => () => {
    if (unclaimed.current) void gateway.discardExport(unclaimed.current).catch(() => {});
  }, [gateway]);
  useEffect(() => {
    if (!ticket || requested) return;
    const timer = window.setTimeout(() => setExpired(true), ticket.expiresInSeconds * 1000);
    return () => window.clearTimeout(timer);
  }, [ticket, requested]);
  const prepare = async () => {
    if (active.current) return;
    active.current = true;
    setBusy(true); setError("");
    try {
      if (unclaimed.current) await gateway.discardExport(unclaimed.current);
      unclaimed.current = undefined;
      setTicket(undefined);
      const result = await gateway.prepareExport(project.id);
      unclaimed.current = result.token;
      setTicket(result); setRequested(false); setExpired(false);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "项目打包失败，请重试。");
    } finally {
      active.current = false; setBusy(false);
    }
  };
  return <Dialog open icon="save" title="导出项目" onClose={() => { if (!active.current) onClose(); }}>
    <div className="project-export-dialog" aria-busy={busy}>
      <strong className="project-export-title">{project.title}</strong>
      <p className="project-export-status" role="status">
        {busy ? "正在打包项目…" : requested ? "已交给浏览器下载，请在下载列表确认是否完成。"
          : expired ? "下载已过期，请重新打包。" : ticket ? "项目包已准备好。"
            : "包含项目、任务、素材和生成历史，不包含模型及连接凭据。"}
      </p>
      {error && <p className="project-export-error" role="alert">{error}</p>}
      <footer className="project-export-actions">
        <Button disabled={busy} onClick={onClose}>关闭</Button>
        {ticket && !expired && !requested && !busy ? <a className="project-export-download"
          href={gateway.downloadUrl(ticket.token)} download="shotmill-project.zip" target="_blank" rel="noopener noreferrer"
          onClick={() => { unclaimed.current = undefined; setRequested(true); }}>下载 ZIP</a>
          : <Button variant="accent" disabled={busy} onClick={() => void prepare()}>
            {ticket ? "重新打包" : "打包项目"}
          </Button>}
      </footer>
    </div>
  </Dialog>;
}
