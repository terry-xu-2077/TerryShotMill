import { useEffect, useMemo, useRef } from "react";
import { Pause, Play } from "lucide-react";
import type { GenerationTask, Result } from "../../domain/storyboard";
import type { DirectorPlaybackState } from "./DirectorWorkspace";

const FPS = 24;

export function TimelinePlayer({ tasks, results, playback, onToggle }: {
  tasks: GenerationTask[];
  results: Result[];
  playback: DirectorPlaybackState;
  onToggle: () => void;
}) {
  const videos = useRef(new Map<string, HTMLVideoElement>());
  const videoRefs = useRef(new Map<string, (node: HTMLVideoElement | null) => void>());
  const videoRef = (id: string) => {
    let callback = videoRefs.current.get(id);
    if (!callback) {
      callback = node => { if (node) videos.current.set(id, node); else { videos.current.get(id)?.pause(); videos.current.delete(id); } };
      videoRefs.current.set(id, callback);
    }
    return callback;
  };
  const resultById = useMemo(() => new Map(results.map(result => [result.id, result])), [results]);
  const current = tasks.find(task => task.id === playback.clipId);
  const currentResult = current?.primaryResultId ? resultById.get(current.primaryResultId) : undefined;
  const following = tasks.find(task => task.id === playback.nextClipId) ?? (current && [...tasks]
    .filter(task => (task.timelineStartSeconds ?? 0) > (current.timelineStartSeconds ?? 0))
    .sort((a, b) => (a.timelineStartSeconds ?? 0) - (b.timelineStartSeconds ?? 0))[0]);
  const followingResult = following?.primaryResultId ? resultById.get(following.primaryResultId) : undefined;
  const entries = [currentResult?.videoUrl ? { id: current!.id, result: currentResult } : null,
    followingResult?.videoUrl ? { id: following!.id, result: followingResult } : null].filter((entry): entry is { id: string; result: Result } => Boolean(entry));
  const syncVideo = (video: HTMLVideoElement | undefined) => {
    if (!video || video.readyState < HTMLMediaElement.HAVE_METADATA) return;
    const position = Math.max(0, (playback.frame - playback.clipStart) / FPS);
    if (Number.isFinite(video.duration)) {
      const target = Math.min(position, Math.max(0, video.duration - 0.04));
      if (Math.abs(video.currentTime - target) > (playback.playing ? 0.18 : 0.02)) video.currentTime = target;
    } else if (Math.abs(video.currentTime - position) > 0.18) video.currentTime = position;
    if (playback.playing && video.paused) void video.play().catch(() => {});
    if (!playback.playing && !video.paused) video.pause();
  };
  useEffect(() => {
    for (const [id, video] of videos.current) {
      if (id === playback.clipId && currentResult?.videoUrl) syncVideo(video);
      else if (!video.paused) video.pause();
    }
  });
  return <div className="director-preview" aria-label="时间线视频预览" data-frame={playback.frame}>
    <button type="button" className="director-preview-screen" onClick={() => {
      const video = playback.clipId ? videos.current.get(playback.clipId) : undefined;
      if (video && playback.playing) video.pause();
      else if (video) void video.play().catch(() => {});
      onToggle();
    }} aria-label={playback.playing ? "暂停时间线播放" : "播放时间线"}>
      {entries.map(entry => <video key={entry.id} ref={videoRef(entry.id)}
        src={entry.result.videoUrl} poster={entry.result.previewUrl} preload="auto" playsInline
        className={entry.id === playback.clipId ? "is-active" : ""}
        onLoadedData={event => { if (entry.id === playback.clipId) syncVideo(event.currentTarget); }} />)}
      {!currentResult?.videoUrl && (current?.storyboardFrame.previewUrl
        ? <img src={current.storyboardFrame.previewUrl} alt="" />
        : <span className="director-preview-empty">{current ? "当前片段暂无视频" : "拖动时间线选择播放位置"}</span>)}
      <span className="director-preview-toggle" aria-hidden="true">{playback.playing ? <Pause size={34} fill="currentColor" /> : <Play size={34} fill="currentColor" />}</span>
    </button>
  </div>;
}
