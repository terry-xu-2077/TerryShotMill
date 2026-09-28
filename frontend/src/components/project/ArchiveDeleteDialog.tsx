import { useRef, useState } from "react";
import type { ArchivedResult, ResultArchiveGateway } from "../../gateways/resultArchiveGateway";
import { Button } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";

export function ArchiveDeleteDialog({ gateway, result, onClose, onDeleted }: {
  gateway: ResultArchiveGateway; result: ArchivedResult;
  onClose: () => void; onDeleted: (id: string) => void;
}) {
  const submitting = useRef(false);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async () => {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true); setError("");
    try { await gateway.delete(result.id); }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败，请重试。");
      submitting.current = false; setBusy(false); return;
    }
    onDeleted(result.id);
  };
  return <Dialog open icon="delete" title="永久删除归档结果" initialFocusRef={cancelRef} onClose={() => {
    if (!submitting.current) onClose();
  }}>
    <div className="result-archive-browser">
      <p className="result-archive-copy">删除“{result.sourceTaskTitle}”的此版本归档？删除后无法从归档中恢复。原任务结果及已导入其他项目的资产不受影响。</p>
      {error && <p role="alert">{error}</p>}
      <footer className="result-archive-actions">
        <Button ref={cancelRef} disabled={busy} onClick={onClose}>取消</Button>
        <Button disabled={busy} onClick={() => void submit()}>{busy ? "正在删除…" : "永久删除"}</Button>
      </footer>
    </div>
  </Dialog>;
}
