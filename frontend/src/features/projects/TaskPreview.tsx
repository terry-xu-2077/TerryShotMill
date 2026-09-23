import { BrandPlaceholder } from "../../components/BrandPlaceholder";

export function TaskPreview({ previewUrl, compact = false, durationSeconds }: {
  previewUrl?: string;
  compact?: boolean;
  durationSeconds?: number;
}) {
  return (
    <div className={`task-preview ${compact ? "is-compact" : ""}`} style={previewUrl ? { backgroundImage: `url("${previewUrl}")` } : undefined}>
      {!previewUrl && <BrandPlaceholder />}
      {typeof durationSeconds === "number" && Number.isFinite(durationSeconds) && durationSeconds > 0 && (
        <span className="task-preview-duration" aria-hidden="true">{durationSeconds} 秒</span>
      )}
    </div>
  );
}
