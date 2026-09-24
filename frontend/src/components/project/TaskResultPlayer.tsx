import { BoolSwitch } from "../../ui/BoolSwitch";
import { useRef, useState } from "react";
import { SkipBack, SkipForward } from "lucide-react";
import { Button } from "../../ui/primitives";
import type { Result } from "../../domain/storyboard";
import "./TaskResultPlayer.css";

export type PlaybackEntry = { result: Result; taskNumber: string; taskId?: string; title?: string };
export function TaskResultPlayer({ result, taskNumber, playlist, onCurrentChange, onClose }: {
  result: Result;
  taskNumber: string;
  playlist?: PlaybackEntry[];
  onCurrentChange?: (entry: PlaybackEntry) => void;
  onClose: () => void;
}) {
  // Freeze the review sequence while playing; background updates must not replace a clip.
  const [entries] = useState(() => playlist?.length ? playlist : [{ result, taskNumber }]);
  const [index, setIndex] = useState(() => Math.max(0, entries.findIndex(entry => entry.result.id === result.id)));
  const [slots, setSlots] = useState(() => [index, index + 1 < entries.length ? index + 1 : null]);
  const [active, setActive] = useState(0);
  const videos = useRef<Array<HTMLVideoElement | null>>([]);
  const pending = useRef<{ slot: number; index: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [continuous, setContinuous] = useState(true);
  const [error, setError] = useState("");
  const [media, setMedia] = useState<Record<number, { width: number; height: number; duration: number }>>({});
  const info = media[index];

  function startStandby(slot: number) {
    const video = videos.current[slot];
    if (!video || pending.current?.slot !== slot) return;
    const current = videos.current[active];
    if (current) {
      video.volume = current.volume;
      video.muted = current.muted;
      video.playbackRate = current.playbackRate;
      current.pause();
    }
    void video.play().catch(() => {
      if (pending.current?.slot !== slot) return;
      pending.current = null;
      setLoading(false);
      setError("播放未能开始，请再次点击上一段或下一段重试。");
    });
  }
  function go(next: number) {
    if (next < 0 || next >= entries.length || pending.current) return;
    const slot = 1 - active;
    setError("");
    setLoading(true);
    pending.current = { slot, index: next };
    if (slots[slot] === next && videos.current[slot]) {
      // The preloaded slot is already at its decoded first frame. Seeking to zero
      // again flushes that frame and introduces a visible stall at every cut.
      if (videos.current[slot]!.currentTime > 0) videos.current[slot]!.currentTime = 0;
      startStandby(slot);
    } else setSlots(current => current.map((value, i) => i === slot ? next : value));
  }
  function reveal(slot: number) {
    const next = pending.current;
    if (!next || next.slot !== slot) return;
    pending.current = null;
    setIndex(next.index);
    setActive(slot);
    setLoading(false);
    setSlots(current => current.map((value, i) => i === slot ? value : next.index + 1 < entries.length ? next.index + 1 : null));
    onCurrentChange?.(entries[next.index]);
  }
  return (
    <div className="task-playback-dialog">
      <div className="task-player-screen">
        {slots.map((entryIndex, slot) => <video key={slot}
          ref={element => { videos.current[slot] = element; }}
          className={`task-player-video${slot === active ? " is-active" : ""}`}
          aria-hidden={slot !== active} tabIndex={slot === active ? 0 : -1}
          controls={slot === active} autoPlay={slot === active} playsInline preload="auto"
          poster={entryIndex === null ? undefined : entries[entryIndex]?.result.previewUrl}
          src={entryIndex === null ? undefined : entries[entryIndex]?.result.videoUrl}
          onLoadedMetadata={event => {
            const video = event.currentTarget;
            if (entryIndex !== null && video.videoWidth > 0 && Number.isFinite(video.duration)) {
              setMedia(current => ({ ...current, [entryIndex]: { width: video.videoWidth, height: video.videoHeight, duration: video.duration } }));
            }
          }}
          onCanPlay={() => { if (pending.current?.slot === slot) startStandby(slot); }}
          // "playing" already guarantees a playable frame. Waiting for an
          // additional video-frame callback held the outgoing frame ~100 ms.
          onPlaying={() => reveal(slot)}
          onEnded={() => { if (slot === active && continuous) go(index + 1); }}
          onError={() => {
            if (slot !== active && pending.current?.slot !== slot) return;
            pending.current = null;
            setLoading(false);
            setError("视频加载失败，可切换其他任务后重试。");
          }}
        />)}
        {loading && <span className="task-player-loading" role="status">正在准备下一段…</span>}
      </div>
      <div className="task-player-transport">
        <Button aria-label="上一个视频" disabled={index === 0 || loading} onClick={() => go(index - 1)}><SkipBack size={17} />上一个</Button>
        <span className="task-player-position">{index + 1} / {entries.length}</span>
        <Button aria-label="下一个视频" disabled={index === entries.length - 1 || loading} onClick={() => go(index + 1)}>下一个<SkipForward size={17} /></Button>
        <div className="task-player-continuous" role="group" aria-label="无缝连续播放"><span>无缝连续播放</span><BoolSwitch value={continuous ? "yes" : "no"} onChange={value => setContinuous(value === "yes")} /></div>
      </div>
      {error && <p className="task-player-error" role="alert">{error}</p>}
      <footer>
        <span>{entries[index].taskNumber}{info && ` · ${info.width} × ${info.height} · ${Number(info.duration.toFixed(2))} 秒`}</span>
        <Button onClick={onClose}>关闭</Button>
      </footer>
    </div>
  );
}
