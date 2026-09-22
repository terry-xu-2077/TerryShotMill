import { useState } from "react";
import { Dialog } from "../../ui/overlay";

export function TaskRiskSticker({ warnings }: { warnings: string[] }) {
  const [open, setOpen] = useState(false);
  if (!warnings.length) return null;
  return <>
    <button type="button" className="task-new-sticker task-risk-sticker" aria-label="查看任务生成风险"
      onClick={event => { event.stopPropagation(); setOpen(true); }}>
      <span className="task-new-sticker-word">!</span>
    </button>
    <Dialog open={open} icon="warning" title="生成风险" onClose={() => setOpen(false)}>
      <ul>{warnings.map(message => <li key={message}>{message}</li>)}</ul>
      <p>可以继续生成，提交前会再次列出这些风险。</p>
    </Dialog>
  </>;
}
