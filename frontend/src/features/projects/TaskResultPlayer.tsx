import { useState } from "react";
import { Button } from "terry-react-ui-library";
import type { Result } from "../../domain/storyboard";

export function TaskResultPlayer({ result, taskNumber, onClose }: {
  result: Result;
  taskNumber: string;
  onClose: () => void;
}) {
  const [media, setMedia] = useState<{ width: number; height: number; duration: number }>();
  return (
    <div className="task-playback-dialog">
      <video controls autoPlay={false} poster={result.previewUrl} src={result.videoUrl}
        onLoadedMetadata={(event) => {
          const video = event.currentTarget;
          if (video.videoWidth > 0 && video.videoHeight > 0 && Number.isFinite(video.duration)) {
            setMedia({ width: video.videoWidth, height: video.videoHeight, duration: video.duration });
          }
        }}
      />
      <footer>
        <span>{taskNumber}{media && ` · ${media.width} × ${media.height} · ${Number(media.duration.toFixed(2))} 秒`}</span>
        <Button onClick={onClose}>关闭</Button>
      </footer>
    </div>
  );
}
