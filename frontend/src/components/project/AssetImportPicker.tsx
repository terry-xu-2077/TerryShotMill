import { useEffect, useState } from "react";
import { assetTransferGateway, type AssetTransferGateway, type ImportCandidate } from "../../gateways/assetTransferGateway";
import { Button, Checkbox } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";
import "./AssetImportPicker.css";

const kindLabels = { asset: "项目资产", result: "生成结果" };
const keyOf = (item: ImportCandidate) => `${item.kind}:${item.id}`;

export function AssetImportPicker({ projectId, gateway = assetTransferGateway, onClose, onSelect }: {
  projectId: string; gateway?: AssetTransferGateway; onClose: () => void; onSelect: (items: ImportCandidate[]) => void;
}) {
  const [items, setItems] = useState<ImportCandidate[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(""); setSelected(new Set());
    gateway.candidates(projectId).then(values => { if (!cancelled) setItems(values); })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "来源加载失败"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId, gateway, attempt]);
  return <Dialog open icon="assets" title="从其他项目导入" onClose={onClose}>
    <div className="asset-import-picker">
      <p>选中后加入当前草稿，保存项目配置时复制为独立资产。取消配置不会导入。</p>
      {loading && <p role="status">正在加载…</p>}
      {error && <div role="alert">{error}<Button onClick={() => setAttempt(value => value + 1)}>重试</Button></div>}
      {!loading && !error && !items.length && <p>没有可导入的资产或生成结果。</p>}
      <div className="asset-import-candidates" aria-label="可导入内容">
        {!loading && !error && items.map(item => <div className="asset-import-candidate" key={keyOf(item)}>
          <Checkbox checked={selected.has(keyOf(item))} ariaLabel={`选择 ${item.sourceProjectTitle} · ${item.name} · ${kindLabels[item.kind]}`} onChange={checked => {
            setSelected(current => { const next = new Set(current); if (checked) next.add(keyOf(item)); else next.delete(keyOf(item)); return next; });
          }} />
          {item.previewUrl && <img src={item.previewUrl} alt="" />}
          <div className="asset-import-description"><strong>{item.name}</strong><span>{item.sourceProjectTitle} · {kindLabels[item.kind]}</span>
            <time dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleString("zh-CN")}</time></div>
        </div>)}
      </div>
      <footer><span>已选 {selected.size} 项</span><Button onClick={onClose}>取消</Button>
        <Button variant="accent" disabled={loading || !!error || !selected.size} onClick={() => {
          onSelect(items.filter(item => selected.has(keyOf(item)))); onClose();
        }}>加入项目草稿</Button></footer>
    </div>
  </Dialog>;
}
