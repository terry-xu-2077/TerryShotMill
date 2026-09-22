import { AlertTriangle, CheckCircle2, Sparkles, Video, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Checkbox } from "terry-react-ui-library";

import type { PromptBatchEligibility, VideoBatchEligibility } from "../../gateways/batchReviewGateway";
import { Dialog } from "../../ui/overlay";

export type PromptBatchOptions = {
  includeProjectBackground: boolean;
  includePreviousTaskSummary: boolean;
};

export function BatchActionBar({
  selectedCount,
  onEnhance,
  onGenerate,
  onClear,
  enhanceDisabled = false,
  generateDisabled = false,
}: {
  selectedCount: number;
  onEnhance: () => void;
  onGenerate: () => void;
  onClear: () => void;
  enhanceDisabled?: boolean;
  generateDisabled?: boolean;
}) {
  if (selectedCount < 1) return null;

  return (
    <div className="batch-action-bar" role="region" aria-label="批量操作">
      <strong>已选择 {selectedCount} 项</strong>
      <div className="batch-action-bar-actions">
        <Button disabled={enhanceDisabled} onClick={onEnhance}><Sparkles size={14} /> AI 增强</Button>
        <Button disabled={generateDisabled} onClick={onGenerate}><Video size={14} /> 生成视频</Button>
        <Button onClick={onClear}><X size={14} /> 取消选择</Button>
      </div>
    </div>
  );
}

export function BatchPromptDialog({
  open,
  taskCount,
  eligibility,
  loading = false,
  onRetry,
  aiLabel = "正在读取增强配置…",
  projectBackgroundAvailable,
  busy = false,
  error = "",
  onClose,
  onConfirm,
}: {
  open: boolean;
  taskCount: number;
  eligibility?: PromptBatchEligibility;
  loading?: boolean;
  onRetry?: () => void;
  aiLabel?: string;
  projectBackgroundAvailable: boolean;
  busy?: boolean;
  error?: string;
  onClose: () => void;
  onConfirm?: (options: PromptBatchOptions) => void;
}) {
  const [includeProjectBackground, setIncludeProjectBackground] = useState(projectBackgroundAvailable);
  const [includePreviousTaskSummary, setIncludePreviousTaskSummary] = useState(false);
  const eligibleCount = eligibility?.eligibleTaskIds.length ?? 0;
  const skippedCounts = new Map<string, number>();
  eligibility?.skipped.forEach(item => skippedCounts.set(item.message, (skippedCounts.get(item.message) ?? 0) + 1));

  useEffect(() => {
    if (!open) return;
    setIncludeProjectBackground(projectBackgroundAvailable);
    setIncludePreviousTaskSummary(false);
  }, [open, projectBackgroundAvailable]);

  return (
    <Dialog open={open} icon="enhance" title="批量 AI 增强" onClose={onClose}>
      <div className="batch-prompt-dialog">
        {error && <p className="batch-prompt-error" role="alert">{error}</p>}
        <div className="batch-prompt-summary">
          <strong>已选择 {taskCount} 个任务</strong>
          <span>AI：{aiLabel}</span>
        </div>

        <div className="batch-prompt-eligibility" aria-label="增强资格" aria-live="polite">
          {loading ? <span>正在检查任务状态…</span> : eligibility ? <>
            <div className="is-ready"><CheckCircle2 size={14} /><span>{eligibleCount} 个任务可增强</span></div>
            {[...skippedCounts.entries()].map(([message, count]) => <div key={message} className="is-skipped"><AlertTriangle size={14} /><span>{count} 个任务{message}，不会提交</span></div>)}
          </> : <Button onClick={onRetry} disabled={!onRetry || busy}>重试检查</Button>}
        </div>

        <div className="batch-prompt-options" aria-label="增强上下文">
          <label>
            <span>项目背景</span>
            <Checkbox
              checked={includeProjectBackground}
              disabled={!projectBackgroundAvailable || busy}
              onChange={setIncludeProjectBackground}
              ariaLabel="项目背景"
            />
          </label>
          <label>
            <span>上一任务摘要</span>
            <Checkbox
              checked={includePreviousTaskSummary}
              disabled={busy}
              onChange={setIncludePreviousTaskSummary}
              ariaLabel="上一任务摘要"
            />
          </label>
        </div>

        <div className="batch-prompt-order">
          <span>执行顺序</span>
          <strong>按当前任务顺序</strong>
        </div>

        <footer>
          <Button disabled={busy} onClick={onClose}>取消</Button>
          {eligibility && onRetry && <Button disabled={busy || loading} onClick={onRetry}>重新检查</Button>}
          <Button
            variant="accent"
            disabled={!onConfirm || eligibleCount < 1 || loading || busy}
            onClick={() => onConfirm?.({ includeProjectBackground, includePreviousTaskSummary })}
          >
            {busy ? "提交中…" : "开始增强"}
          </Button>
        </footer>
      </div>
    </Dialog>
  );
}

function reasonLabel(reason: string) {
  if (reason === "busy") return "正在运行";
  if (reason === "invalid-params") return "参数无效";
  return reason;
}

export function BatchVideoDialog({
  open,
  title = "批量生成视频",
  error = "",
  selectedCount,
  eligibility,
  loading = false,
  submitting = false,
  onClose,
  onConfirm,
}: {
  open: boolean;
  selectedCount: number;
  title?: string;
  error?: string;
  eligibility?: VideoBatchEligibility;
  loading?: boolean;
  submitting?: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const skippedByReason = new Map<string, number>();
  eligibility?.skipped.forEach((item) => {
    skippedByReason.set(item.reason, (skippedByReason.get(item.reason) ?? 0) + 1);
  });
  const eligibleCount = eligibility?.eligibleTaskIds.length ?? 0;

  return (
    <Dialog open={open} icon="video" title={title} onClose={onClose}>
      <div className="batch-video-dialog">
        {error && <p className="batch-video-error" role="alert">{error}</p>}
        <div className="batch-video-summary-grid">
          <div><span>已选择</span><strong>{selectedCount}</strong></div>
          <div className="is-ready"><span>可生成</span><strong>{loading ? "…" : eligibleCount}</strong></div>
        </div>

        <div className="batch-video-eligibility" aria-label="生成资格">
          {loading ? (
            <span>正在检查任务状态…</span>
          ) : (
            <>
              <div className="is-ready"><CheckCircle2 size={14} /><span>{eligibleCount} 个任务将进入视频生成队列</span></div>
              {!!eligibility?.warnings?.length && <section className="generation-risk-notice" aria-label="生成前风险提醒">
                <strong>以下风险不阻止生成，请确认后继续</strong>
                <ul>{eligibility.warnings.map(item => <li key={`${item.taskId}:${item.message}`}><b>{item.title}</b>：{item.message}</li>)}</ul>
              </section>}
              {[...skippedByReason.entries()].map(([reason, count]) => (
                <div key={reason} className="is-skipped"><AlertTriangle size={14} /><span>{count} 个{reasonLabel(reason)}，不会提交</span></div>
              ))}
              {[...new Set(eligibility?.skipped.map((item) => item.message).filter(Boolean))].map((message) => (
                <div key={message} className="is-skipped"><span>{message}</span></div>
              ))}
            </>
          )}
        </div>

        <footer>
          <Button disabled={submitting} onClick={onClose}>取消</Button>
          <Button
            variant="accent"
            disabled={loading || submitting || eligibleCount < 1}
            onClick={onConfirm}
          >
            {submitting ? "提交中…" : `生成 ${eligibleCount} 个视频`}
          </Button>
        </footer>
      </div>
    </Dialog>
  );
}
