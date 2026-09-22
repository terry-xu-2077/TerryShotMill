import { useMemo, useRef, useState } from "react";
import { Button, Select } from "terry-react-ui-library";
import type { ProjectAsset, Result } from "../../domain/storyboard";
import type { ProjectCoverSelection } from "../../gateways/projectGateway";
import { Dialog } from "../../ui/overlay";

export function ProjectCoverEditor({ assets, results, coverUrl, automaticCoverUrl, previewUrl, custom, value, onChange }: {
  assets: ProjectAsset[]; results: Result[]; coverUrl?: string; custom: boolean;
  automaticCoverUrl?: string; previewUrl?: string;
  value?: ProjectCoverSelection; onChange: (selection: ProjectCoverSelection, preview?: string) => void;
}) {
  const [mode, setMode] = useState<"asset" | "video" | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [frameReady, setFrameReady] = useState(false);
  const [error, setError] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  const candidates = useMemo(() => mode === "asset"
    ? assets.filter((item) => item.mediaType === "image").map((item) => ({ id: `asset:${item.id}`, name: item.name, url: item.mediaUrl || item.previewUrl || "", assetId: item.id, resultId: undefined }))
    : [
      ...assets.filter((item) => item.mediaType === "video").map((item) => ({ id: `asset:${item.id}`, name: item.name, url: item.mediaUrl || (item.sourceFile ? item.previewUrl : "") || "", assetId: item.id, resultId: undefined })),
      ...results.filter((item) => item.videoUrl).map((item, index) => ({ id: `result:${item.id}`, name: `生成视频 ${index + 1}`, url: item.videoUrl, resultId: item.id, assetId: undefined })),
    ], [assets, results, mode]);
  const selected = candidates.find((item) => item.id === selectedId) ?? candidates[0];
  const open = (next: "asset" | "video") => { setMode(next); setSelectedId(""); setSeconds(0); setError(""); setFrameReady(false); };
  const choose = () => {
    if (!selected || !mode) return;
    let chosenPreview = selected.url;
    let chosenSeconds = 0;
    if (mode === "video") {
      const player = video.current;
      if (!player || player.readyState < 2 || !player.videoWidth || player.seeking) return;
      try {
        const canvas = document.createElement("canvas");
        canvas.width = player.videoWidth; canvas.height = player.videoHeight;
        canvas.getContext("2d")!.drawImage(player, 0, 0);
        chosenPreview = canvas.toDataURL("image/png");
        chosenSeconds = player.currentTime;
      } catch { setError("无法预览该画面，请检查视频后重试。"); return; }
    }
    onChange({ kind: mode, assetId: selected.assetId, resultId: selected.resultId, ...(mode === "video" ? { seconds: chosenSeconds } : {}) }, chosenPreview);
    setMode(null);
  };
  const automatic = value ? value.kind === "auto" : !custom;
  const displayedCover = value?.kind === "auto" ? automaticCoverUrl : previewUrl || coverUrl;
  return <div className="project-cover-editor">
    <div className="project-cover-current">{displayedCover && <img src={displayedCover} alt="项目封面" />}</div>
    <div className="project-cover-actions"><strong>项目封面 · {automatic ? "自动跟随首个任务" : "自定义"}</strong>
      <div className="project-cover-buttons"><Button onClick={() => open("asset")}>选择图片</Button><Button onClick={() => open("video")}>从视频截取</Button><Button disabled={automatic} onClick={() => onChange({ kind: "auto" })}>恢复自动</Button></div>
    </div>
    <Dialog open={mode !== null} icon={mode === "asset" ? "image" : "camera"} title={mode === "asset" ? "选择封面图片" : "截取视频封面"} onClose={() => setMode(null)} size="wide">
      <div className="project-cover-picker">
        <Select ariaLabel="封面来源" value={selected?.id ?? ""} onChange={(id) => { setSelectedId(id); setSeconds(0); setError(""); setFrameReady(false); }} options={candidates.map((item) => ({ value: item.id, label: item.name }))} />
        {selected ? mode === "video" ? <video key={selected.id} ref={video} controls playsInline preload="auto" src={selected.url} onLoadedData={() => setFrameReady(true)} onSeeking={() => setFrameReady(false)} onSeeked={() => setFrameReady(true)} onTimeUpdate={(event) => setSeconds(event.currentTarget.currentTime)} onError={() => { setError("视频无法播放，请重新选择。"); setFrameReady(false); }} /> : <img src={selected.url} alt={selected.name} /> : <p>没有可用的{mode === "asset" ? "图片" : "视频"}。</p>}
        <footer>{error ? <span role="alert">{error}</span> : mode === "video" && <span>当前画面 {seconds.toFixed(2)} 秒</span>}<Button disabled={!selected || Boolean(error) || (mode === "video" && !frameReady)} onClick={choose}>{mode === "video" ? "使用当前画面" : "设为封面"}</Button></footer>
      </div>
    </Dialog>
  </div>;
}
