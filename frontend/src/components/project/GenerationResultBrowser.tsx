import type { GenerationTask, Result } from "../../domain/storyboard";
import type { DirectorProject } from "./projectTypes";
import { TaskPreview } from "./TaskPreview";

export function GenerationResultBrowser({ project, onPlay }: {
  project: DirectorProject;
  onPlay: (result: Result, task: GenerationTask) => void;
}) {
  const tasks = new Map(project.snapshot.tasks.map(task => [task.id, task]));
  const jobs = new Map(project.snapshot.jobs.map(job => [job.id, job]));
  const entries = project.snapshot.results.flatMap(result => {
    const task = tasks.get(jobs.get(result.jobId)?.taskId ?? "");
    return result.videoUrl && task ? [{ result, task }] : [];
  });
  return <div className="task-card-view generation-result-browser" aria-label="生成结果浏览">
    {!entries.length && <p className="task-results-empty">尚无生成结果。打开时间线生成片段后，可在这里浏览。</p>}
    {entries.map(({ result, task }) => {
      const sceneId = project.snapshot.taskPlacements.find(item => item.taskId === task.id)?.sceneId;
      const timeline = project.snapshot.scenes.find(item => item.id === sceneId);
      const version = entries.filter(item => item.task.id === task.id).findIndex(item => item.result.id === result.id) + 1;
      const duration = result.metadata.durationSeconds;
      return <button key={result.id} type="button" className="task-card-item generation-result-card" onClick={() => onPlay(result, task)} aria-label={`播放结果 · ${task.title} · 版本 ${version}`}>
        <div className="task-card-preview-wrap"><TaskPreview previewUrl={result.previewUrl} /></div>
        <div className="task-card-heading"><strong>{task.title}</strong></div>
        <p>{timeline?.title || "时间线"} · 版本 {version}{task.primaryResultId === result.id ? " · 当前采用" : ""}</p>
        <footer>{typeof duration === "number" ? `${duration.toFixed(1)} 秒` : "视频结果"}</footer>
      </button>;
    })}
  </div>;
}
