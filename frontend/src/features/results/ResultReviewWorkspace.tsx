import { useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { Check, Eye, History, Pencil, RefreshCw, Star, X } from "lucide-react";
import { Button, StatusPill } from "terry-react-ui-library";

import type { ResultReviewState, StoryboardDomainSnapshot } from "../../domain/storyboard";
import {
  approveAllPendingResults,
  requestTaskRegeneration,
  setResultReviewState,
  setTaskPrimaryResult,
} from "../storyboard/storyboardExecution";
import { Dialog } from "../../ui/overlay";

type ResultFilter = "all" | ResultReviewState;

const reviewLabel: Record<ResultReviewState, string> = {
  pending: "待审核",
  approved: "已通过",
  rejected: "已拒绝",
};

const reviewTone: Record<ResultReviewState, "active" | "normal" | "danger"> = {
  pending: "active",
  approved: "normal",
  rejected: "danger",
};

export function ResultReviewWorkspace({
  snapshot,
  onChange,
  onEditTask,
}: {
  snapshot: StoryboardDomainSnapshot;
  onChange: Dispatch<SetStateAction<StoryboardDomainSnapshot>>;
  onEditTask: (taskId: string) => void;
}) {
  const [filter, setFilter] = useState<ResultFilter>("pending");
  const [previewResultId, setPreviewResultId] = useState<string | null>(null);
  const [historyTaskId, setHistoryTaskId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const jobsById = useMemo(() => new Map(snapshot.jobs.map((job) => [job.id, job])), [snapshot.jobs]);
  const tasksById = useMemo(() => new Map(snapshot.tasks.map((task) => [task.id, task])), [snapshot.tasks]);
  const records = useMemo(() => snapshot.results
    .map((result) => {
      const job = jobsById.get(result.jobId);
      const task = job ? tasksById.get(job.taskId) : undefined;
      return job && task ? { result, job, task } : undefined;
    })
    .filter((record): record is NonNullable<typeof record> => Boolean(record))
    .sort((left, right) => right.job.createdAt.localeCompare(left.job.createdAt)), [jobsById, snapshot.results, tasksById]);
  const latestResultByTask = useMemo(() => {
    const latest = new Map<string, string>();
    records.forEach(({ result, task }) => {
      if (!latest.has(task.id)) latest.set(task.id, result.id);
    });
    return latest;
  }, [records]);
  const visibleRecords = records.filter(({ result }) => filter === "all" || result.reviewState === filter);
  const pendingCount = records.filter(({ result }) => result.reviewState === "pending").length;
  const previewRecord = records.find(({ result }) => result.id === previewResultId);
  const historyRecords = records.filter(({ task }) => task.id === historyTaskId);

  const approveAll = () => {
    const next = approveAllPendingResults(snapshot);
    onChange(next.snapshot);
    setMessage(`已通过 ${next.approvedResultIds.length} 个待审核 Result；历史记录保持不变`);
  };

  return (
    <section className="result-review-workspace" aria-label="Result Review">
      <header className="result-review-head">
        <div>
          <span className="eyebrow">TASK RESULT REVIEW</span>
          <h1>结果审核墙</h1>
          <p>每个 Result 都属于完整 Generation Task；多镜头 Task 仍作为一个完整结果审核。</p>
        </div>
        <div className="result-review-summary">
          <span><strong>{records.length}</strong> Results</span>
          <span><strong>{pendingCount}</strong> Pending</span>
          <Button variant="accent" onClick={approveAll} disabled={pendingCount === 0}>通过全部待审核</Button>
        </div>
      </header>

      <nav className="result-review-filters" aria-label="Result 筛选">
        {(["pending", "all", "approved", "rejected"] as const).map((value) => (
          <button key={value} type="button" className={filter === value ? "is-active" : ""} onClick={() => setFilter(value)}>
            {value === "all" ? "全部" : reviewLabel[value]}
            <span>{value === "all" ? records.length : records.filter(({ result }) => result.reviewState === value).length}</span>
          </button>
        ))}
      </nav>

      {message && <p className="result-review-message" role="status">{message}</p>}

      {visibleRecords.length > 0 ? (
        <div className="result-review-grid">
          {visibleRecords.map(({ result, job, task }) => {
            const isPrimary = task.primaryResultId === result.id;
            const isLatest = latestResultByTask.get(task.id) === result.id;
            const historyCount = records.filter((record) => record.task.id === task.id).length;
            return (
              <article key={result.id} className={`result-review-card ${isPrimary ? "is-primary" : ""}`} data-result-id={result.id}>
                <button
                  type="button"
                  className="result-review-preview"
                  style={result.previewUrl ? { backgroundImage: `linear-gradient(to top, rgba(6,8,10,.82), transparent 64%), url("${result.previewUrl}")` } : undefined}
                  onClick={() => setPreviewResultId(result.id)}
                  aria-label={`预览 ${result.id}`}
                >
                  <span>{task.visualBeats.length > 1 ? `完整多镜头 Task · ${task.visualBeats.length} Beats` : "完整单镜头 Task Result"}</span>
                  <em><Eye size={13} /> Preview</em>
                  {isPrimary && <strong><Star size={12} /> PRIMARY</strong>}
                  {isLatest && <i>LATEST</i>}
                </button>
                <div className="result-review-content">
                  <header>
                    <div><span>{task.number}</span><h2>{task.title}</h2></div>
                    <StatusPill tone={reviewTone[result.reviewState]}>{reviewLabel[result.reviewState]}</StatusPill>
                  </header>
                  <p>{result.id} · {job.id}</p>
                  <dl>
                    <div><dt>Duration</dt><dd>{String(result.metadata.durationSeconds ?? task.plannedDurationSeconds)}s</dd></div>
                    <div><dt>Profile</dt><dd>{job.generationProfileSnapshot.id}</dd></div>
                    <div><dt>History</dt><dd>{historyCount}</dd></div>
                  </dl>
                  <div className="result-review-actions">
                    <Button onClick={() => onChange((current) => setResultReviewState(current, result.id, "approved"))}><Check size={13} /> 通过</Button>
                    <Button onClick={() => onChange((current) => setResultReviewState(current, result.id, "rejected"))}><X size={13} /> 拒绝</Button>
                    <Button
                      onClick={() => {
                        const changed = setTaskPrimaryResult(snapshot, task.id, result.id);
                        onChange(changed.snapshot);
                        setMessage(changed.changed
                          ? `已将 ${result.id} 设为 Primary；${changed.staleContextLinkIds.length} 条下游 Context 标记为 Stale`
                          : `${result.id} 已是当前 Primary`);
                      }}
                      disabled={result.reviewState !== "approved" || isPrimary}
                    ><Star size={13} /> 设为 Primary</Button>
                    <Button onClick={() => {
                      onChange((current) => requestTaskRegeneration(current, task.id));
                      setMessage(`已请求重新生成 ${task.number}；旧 Job 与 Result 保持不变`);
                    }}><RefreshCw size={13} /> 重新生成</Button>
                    <Button onClick={() => onEditTask(task.id)}><Pencil size={13} /> 编辑 Task</Button>
                    <Button onClick={() => setHistoryTaskId(task.id)}><History size={13} /> 打开历史</Button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="result-review-empty">当前筛选下没有 Result。</div>
      )}

      <Dialog
        open={Boolean(previewRecord)}
        icon="video" title={previewRecord ? `${previewRecord.task.number} · Result Preview` : "Result Preview"}
        description="预览的是完整 Task Result，不会按 Visual Beat 拆成多个结果。"
        onClose={() => setPreviewResultId(null)}
      >
        {previewRecord && (
          <div className="result-preview-dialog">
            <div style={previewRecord.result.previewUrl ? { backgroundImage: `url("${previewRecord.result.previewUrl}")` } : undefined}><Eye size={28} /></div>
            <p>{previewRecord.result.videoUrl}</p>
            <code>{JSON.stringify(previewRecord.result.metadata)}</code>
          </div>
        )}
      </Dialog>

      <Dialog
        open={Boolean(historyTaskId)}
        icon="history" title={historyRecords[0] ? `${historyRecords[0].task.number} · Result History` : "Result History"}
        description="旧 Result 不覆盖；Primary、Latest 与审核状态分别记录。"
        onClose={() => setHistoryTaskId(null)}
      >
        <div className="result-history-list">
          {historyRecords.map(({ result, job, task }, index) => (
            <article key={result.id}>
              <span>Version {historyRecords.length - index}</span>
              <strong>{result.id}</strong>
              <small>{job.createdAt} · {reviewLabel[result.reviewState]}</small>
              {task.primaryResultId === result.id && <em>PRIMARY</em>}
            </article>
          ))}
        </div>
      </Dialog>
    </section>
  );
}
