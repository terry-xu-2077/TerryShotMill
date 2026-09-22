import { Play } from "lucide-react";

export function TaskPreview({ previewUrl, compact = false, durationSeconds }: {
  previewUrl?: string;
  compact?: boolean;
  durationSeconds?: number;
}) {
  return (
    <div className={`task-preview ${compact ? "is-compact" : ""}`} style={previewUrl ? { backgroundImage: `url("${previewUrl}")` } : undefined}>
      {!previewUrl && <Play size={compact ? 22 : 44} />}
      {typeof durationSeconds === "number" && Number.isFinite(durationSeconds) && durationSeconds > 0 && (
        <span className="task-preview-duration" aria-hidden="true">{durationSeconds} 秒</span>
      )}
    </div>
  );
}
