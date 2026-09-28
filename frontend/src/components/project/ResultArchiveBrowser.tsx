import { useEffect, useMemo, useState } from "react";
import type { ArchivedFile, ArchivedResult, ResultArchiveGateway } from "../../gateways/resultArchiveGateway";
import type { ProjectSummary } from "../../gateways/projectGateway";
import { Button, SegmentedControl } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";
import "./ResultArchive.css";
import { ArchiveDeleteDialog } from "./ArchiveDeleteDialog";

export function ResultArchiveBrowser({ gateway, projects, onClose }: {
  gateway: ResultArchiveGateway; projects: ProjectSummary[]; onClose: () => void;
}) {
  const [results, setResults] = useState<ArchivedResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [preview, setPreview] = useState<ArchivedResult | null>(null);
  const [importing, setImporting] = useState<ArchivedResult | null>(null);
  const [deleting, setDeleting] = useState<ArchivedResult | null>(null);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError("");
    gateway.list().then(items => { if (!cancelled) setResults(items); })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "归档加载失败"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [gateway, attempt]);
  const groups = useMemo(() => {
    const grouped = new Map<string, ArchivedResult[]>();
    for (const result of results) grouped.set(result.sourceProjectId, [...(grouped.get(result.sourceProjectId) ?? []), result]);
    return [...grouped.entries()];
  }, [results]);
  return <>
    <Dialog open icon="history" title="生成结果归档" onClose={onClose}>
      <div className="result-archive-browser">
        <p className="result-archive-copy">独立保留的全部生成版本，不受原项目或任务删除影响。</p>
        {loading && <p role="status">正在加载…</p>}
        {error && <div role="alert">{error}<Button onClick={() => setAttempt(value => value + 1)}>重试</Button></div>}
        {!loading && !error && !results.length && <p>暂无归档结果。永久删除任务或项目时，可选择保留生成结果。</p>}
        <div className="result-archive-list" aria-label="归档结果列表">
          {groups.map(([id, items]) => <section key={id} aria-label={`原项目 · ${items[0].sourceProjectTitle}`}>
            <h3>{items[0].sourceProjectTitle}</h3>
            {items.map(result => <div className="result-archive-row" key={result.id}>
              <div className="result-archive-name"><strong>{result.sourceTaskTitle}</strong><time dateTime={result.generatedAt}>{new Date(result.generatedAt).toLocaleString("zh-CN")}</time></div>
              <div className="result-archive-actions"><Button onClick={() => setPreview(result)}>查看结果</Button><Button onClick={() => setImporting(result)}>导入项目</Button><Button onClick={() => setDeleting(result)}>删除归档</Button></div>
            </div>)}
          </section>)}
        </div>
      </div>
    </Dialog>
    {preview && <ArchivedResultPreview result={preview} onClose={() => setPreview(null)} />}
    {importing && <ArchiveImportDialog gateway={gateway} result={importing} projects={projects}
      onClose={() => setImporting(null)} />}
    {deleting && <ArchiveDeleteDialog gateway={gateway} result={deleting}
      onClose={() => setDeleting(null)} onDeleted={id => {
        setResults(items => items.filter(item => item.id !== id));
        setDeleting(null);
      }} />}
  </>;
}

function MediaPreview({ file }: { file: ArchivedFile }) {
  const extension = file.filename.split(".").pop()?.toLowerCase();
  if (["png", "jpg", "jpeg", "webp", "gif", "avif"].includes(extension ?? "")) return <img className="result-archive-media" src={file.url} alt={file.filename} />;
  if (["mp4", "webm", "mov", "m4v", "ogv"].includes(extension ?? "")) return <video className="result-archive-media" controls src={file.url} />;
  if (["mp3", "wav", "ogg", "flac", "m4a"].includes(extension ?? "")) return <audio controls src={file.url} />;
  return <p>此格式请下载后查看。</p>;
}

export function ArchivedResultPreview({ result, onClose }: { result: ArchivedResult; onClose: () => void }) {
  const [mode, setMode] = useState("preview");
  const file = result.files.find(item => item.role === "output") ?? result.files[0];
  return <Dialog open icon="video" title={`归档结果 · ${result.sourceTaskTitle}`} onClose={onClose}>
    <div className="result-archive-detail">
      <SegmentedControl value={mode} ariaLabel="归档结果查看模式" options={[
        { value: "preview", label: "预览" }, { value: "metadata", label: "生成信息" },
      ]} onChange={setMode} />
      <div className="result-archive-detail-body">{mode === "preview" ? file && <MediaPreview file={file} />
        : <div className="result-archive-metadata"><p>{result.finalPrompt || "无提示词记录"}</p><pre>{JSON.stringify(result.params, null, 2)}</pre></div>}</div>
      <p className="result-archive-copy">{result.sourceProjectTitle} · {new Date(result.generatedAt).toLocaleString("zh-CN")}</p>
      <div className="result-archive-downloads">{result.files.map((item, index) =>
        <a key={`${item.url}-${index}`} title={item.filename} href={`${item.url}${item.url.includes("?") ? "&" : "?"}download=true`} download={item.filename}>
          下载{item.role === "preview" ? "预览图" : "原文件"}
        </a>)}</div>
    </div>
  </Dialog>;
}

export function ArchiveImportDialog({ gateway, result, projects, onClose }: {
  gateway: ResultArchiveGateway; result: ArchivedResult; projects: ProjectSummary[]; onClose: () => void;
}) {
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [complete, setComplete] = useState(false);
  const available = projects.filter(project => !project.archivedAt && !project.deletedAt);
  const submit = async () => {
    if (!target || busy || complete) return;
    setBusy(true); setError("");
    try { await gateway.importInto(target, result.id); setComplete(true); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "导入失败，请重试"); }
    finally { setBusy(false); }
  };
  return <Dialog open icon="history" title="导入归档结果" onClose={() => { if (!busy) onClose(); }}>
    <div className="result-archive-browser">
      <p className="result-archive-copy">将“{result.sourceTaskTitle}”复制为目标项目的独立资产，归档原件保持不变。</p>
      {complete ? <p role="status">已导入，可在目标项目的项目资产中找到。</p> : <>
        {!available.length && <p>没有可导入的项目，请先新建项目或取消项目归档。</p>}
        <div className="result-archive-targets" aria-label="选择目标项目">{available.map(project =>
          <Button key={project.id} disabled={busy} aria-pressed={target === project.id} onClick={() => setTarget(project.id)}>{project.title}</Button>)}</div>
      </>}
      {error && <p role="alert">{error}</p>}
      <footer className="result-archive-actions"><Button disabled={busy} onClick={onClose}>{complete ? "完成" : "取消"}</Button>
        {!complete && <Button variant="accent" disabled={!target || busy} onClick={() => void submit()}>{busy ? "正在复制…" : "导入"}</Button>}</footer>
    </div>
  </Dialog>;
}
