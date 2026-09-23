import { useEffect, useRef, useState } from "react";
import { ResetButton } from "./primitives";
import type { CSSProperties } from "react";
import "./Slider.css";

export type SliderProps = {
  value: number;
  ariaLabel?: string;
  rawValue?: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  orientation?: "horizontal" | "vertical";
  /**
   * The slider track is an editing aid, not necessarily a hard validation range.
   * When enabled, the numeric input may contain values below `min` or above `max`.
   * The range thumb stays pinned to the nearest end while the numeric value remains exact.
   */
  allowOutOfRangeInput?: boolean;
};

function clampToTrack(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

// Keep the physical control responsive even when its consumer renders a large editor.
// Parent notifications are bounded to ~20 Hz while dragging, and pointer/key/blur commit
// the final value immediately. The numeric field and thumb themselves update locally on
// every native input event.
const EMIT_WINDOW_MS = 48;

export function Slider({
  value,
  ariaLabel,
  rawValue,
  min = 0,
  max = 100,
  step = 1,
  onChange,
  disabled,
  orientation = "horizontal",
  allowOutOfRangeInput = false,
}: SliderProps) {
  const [draftValue, setDraftValue] = useState(value);
  const latestValue = useRef(value);
  const lastEmittedValue = useRef(value);
  const emitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onChangeRef = useRef(onChange);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    // A parent may echo the last throttled value while the pointer has already moved
    // farther locally. Do not roll the thumb backwards in that window. Once there is no
    // newer local draft, normal controlled-prop synchronization resumes.
    const hasNewerLocalDraft = !Object.is(latestValue.current, lastEmittedValue.current);
    if (hasNewerLocalDraft && Object.is(value, lastEmittedValue.current)) return;
    setDraftValue(value);
    latestValue.current = value;
    lastEmittedValue.current = value;
  }, [value]);

  useEffect(() => () => {
    if (emitTimer.current) clearTimeout(emitTimer.current);
  }, []);

  const emitLatest = () => {
    if (emitTimer.current) {
      clearTimeout(emitTimer.current);
      emitTimer.current = null;
    }
    const next = latestValue.current;
    if (Object.is(next, lastEmittedValue.current)) return;
    lastEmittedValue.current = next;
    onChangeRef.current(next);
  };

  const scheduleEmit = () => {
    if (emitTimer.current) return;
    emitTimer.current = setTimeout(() => {
      emitTimer.current = null;
      const next = latestValue.current;
      if (Object.is(next, lastEmittedValue.current)) return;
      lastEmittedValue.current = next;
      onChangeRef.current(next);
    }, EMIT_WINDOW_MS);
  };

  const updateDraft = (next: number) => {
    if (!Number.isFinite(next)) return;
    latestValue.current = next;
    setDraftValue(next);
    scheduleEmit();
  };

  const changed = rawValue !== undefined && draftValue !== rawValue;
  const trackValue = Number.isFinite(draftValue) ? clampToTrack(draftValue, min, max) : min;
  const vertical = orientation === "vertical";

  return <div className={`sm-slider-wrap ${vertical ? "sm-slider-wrap-vertical" : ""}`} onPointerUp={emitLatest} onKeyUp={emitLatest} onBlur={emitLatest}>
    <div className={`sm-slider ${vertical ? "sm-slider-vertical" : ""}`}>
      <div className="sm-slider-track" style={{ "--slider-ratio": max > min ? (trackValue - min) / (max - min) : 0, "--slider-progress": `${max > min ? (trackValue - min) / (max - min) * 100 : 0}%` } as CSSProperties}>
        <div className="sm-slider-fill" />
      <input className="sm-slider-range" aria-label={ariaLabel} disabled={disabled} type="range" min={min} max={max} step={step} value={trackValue} onChange={event => updateDraft(Number(event.target.value))}/>
      </div>
      <input className="sm-slider-number" aria-label={ariaLabel ? `${ariaLabel}数值` : undefined} disabled={disabled} type="number" min={allowOutOfRangeInput ? undefined : min} max={allowOutOfRangeInput ? undefined : max} step={step} value={draftValue} onChange={event => updateDraft(Number(event.target.value))}/>
    </div>
    {rawValue !== undefined && <ResetButton visible={changed} onClick={() => updateDraft(rawValue)}/>} 
  </div>;
}
