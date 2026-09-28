import { useEffect, useState } from "react";
import { readOnlyProjectGateway, type HistoricalResult, type ReadOnlyProjectGateway } from "../../gateways/readOnlyProjectGateway";
import type { TaskEditorView } from "../../gateways/projectGateway";
import { Button, SegmentedControl } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";
import "./ProjectReadOnly.css";

export function TaskReadOnlyDialog({ projectId, taskId, title, gateway = readOnlyProjectGateway, onClose }: {
  projectId: string; taskId: string; title: string; gateway?: ReadOnlyProjectGateway; onClose: () => void;
}) {
  const [results, setResults] = useState<HistoricalResult[]>([]);
  const [task, setTask] = useState<TaskEditorView>();
  const [selected, setSelected] = useState("");
  const [mode, setMode] = useState("results");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError("");
    Promise.all([gateway.task(projectId, taskId), gateway.results(projectId, taskId)]).then(([detail, versions]) => {
      if (cancelled) return;
      setTask(detail); setResults(versions); setSelected(versions[0]?.id ?? "");
    }).catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "任务加载失败"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId, taskId, gateway, attempt]);
  const current = results.find(item => item.id === selected);
  return <Dialog open icon="task" title={`只读任务 · ${title}`} onClose={onClose}>
    <div className="task-readonly-view">
      <SegmentedControl value={mode} ariaLabel="只读任务内容" options={[
        { value: "results", label: "历史结果" }, { value: "prompt", label: "任务内容" },
      ]} onChange={setMode} />
      {loading ? <p role="status">正在加载…</p> : error ? <div role="alert">{error}<Button onClick={() => setAttempt(value => value + 1)}>重试</Button></div> :
        mode === "prompt" ? <div className="task-readonly-copy"><h3>用户提示词</h3><p>{task?.userPrompt || "未填写"}</p>
          <h3>AI 提示词</h3><p>{task?.aiEnhancedPrompt || "未增强"}</p><p>当前使用：{task?.promptSource === "ai" ? "AI 提示词" : "用户提示词"}</p></div>
          : <div className="task-readonly-results">
            <div className="task-readonly-version-list" aria-label="全部生成版本">{results.map((result, index) =>
              <Button key={result.id} aria-pressed={selected === result.id} onClick={() => setSelected(result.id)}>版本 {results.length - index} · {new Date(result.createdAt).toLocaleString("zh-CN")}</Button>)}</div>
            {current ? <><video key={current.id} controls className="task-readonly-video" src={current.videoUrl} poster={current.previewUrl ?? undefined} />
              <a href={current.videoUrl} download>下载当前版本</a></> : <p>此任务尚无生成结果。</p>}
          </div>}
    </div>
  </Dialog>;
}
