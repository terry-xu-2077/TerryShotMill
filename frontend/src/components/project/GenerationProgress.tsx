import type { TaskTiming } from "../../gateways/projectGateway";
import { formatElapsed } from "./taskTiming";

export function TaskProgressLight({ timing }: { timing?: TaskTiming }) {
  if (!timing?.videoRunning) return null;
  const data = timing.generationProgress;
  const available = data && Number.isFinite(data.measuredAt);
  const percent = available ? data.percent : null;
  return <span className={`task-progress-light${percent == null ? " is-indeterminate" : ""}`} role="progressbar" aria-label="当前生成步骤进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent ?? undefined}>
    <span style={percent == null ? undefined : { width: `${Math.min(100, Math.max(0, percent))}%` }} />
  </span>;
}

export function GenerationProgress({ timing, status }: { timing?: TaskTiming; status: string }) {
  const data = timing?.generationProgress;
  const available = data && Number.isFinite(data.measuredAt);
  return <section className="generation-progress-panel" aria-label="生成进度">
    <h3>生成进度 <span>{status}</span></h3>
    {timing?.videoRunning ? <>
      <strong>{available ? data.stage : "等待生成进度更新"}</strong>
      <div className="generation-progress-track"><TaskProgressLight timing={timing} /></div>
      {available && data.total != null && <p>当前步骤 {data.step} / {data.total}</p>}
      <dl><div><dt>生成已用时</dt><dd>{formatElapsed(timing.videoSeconds)}</dd></div>
        <div><dt>当前步骤耗时</dt><dd>{data ? formatElapsed(Date.now()/1000-data.stageStartedAt) : "等待数据"}</dd></div>
        <div><dt>本步骤预计剩余</dt><dd>{available && data.remainingSeconds != null ? `约 ${formatElapsed(data.remainingSeconds)}` : "估算中"}</dd></div></dl>
      <p className="generation-progress-note">进度与预计时间按当前步骤计算，后续处理耗时另计。</p>
    </> : <p>{timing?.videoQueued ? "等待队列调度" : status}</p>}
    {!!data?.stages?.length && <details><summary>已执行步骤</summary><ol>{data.stages.map((step, index) => <li key={index}><span>{step.stage}</span><span>{formatElapsed(step.seconds)}</span></li>)}</ol></details>}
  </section>;
}
