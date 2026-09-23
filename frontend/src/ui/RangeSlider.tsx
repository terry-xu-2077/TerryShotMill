import "./RangeSlider.css";
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

export type RangeSliderProps = {
  value: readonly [number, number];
  min?: number;
  max?: number;
  step?: number;
  minDistance?: number;
  disabled?: boolean;
  variant?: "slider" | "timeline";
  selectionLabel?: string;
  startLabel: string;
  endLabel: string;
  formatValue?: (value: number) => string;
  onChange: (value: [number, number]) => void;
};

export function RangeSlider({ value, min = 0, max = 100, step = 1, minDistance = step,
  disabled = false, variant = "slider", selectionLabel = "Selected interval", startLabel, endLabel, formatValue = String, onChange }: RangeSliderProps) {
  const [draft, setDraft] = useState<[number, number]>([...value]);
  const latest = useRef(draft);
  const callback = useRef(onChange);
  callback.current = onChange;
  const track = useRef<HTMLDivElement>(null);
  const handles = useRef<(HTMLButtonElement | null)[]>([]);
  const drag = useRef<({ pointer: number } & (
    { kind: "edge"; index: 0 | 1; offset: number } |
    { kind: "selection"; origin: number; value: [number, number] }
  )) | null>(null);
  const [dragging, setDragging] = useState<"edge" | "selection" | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const emitted = useRef<[number, number]>([...value]);
  const unavailable = disabled || max <= min;
  const gap = Math.min(max - min, Math.max(0, minDistance));

  useEffect(() => {
    if (drag.current) return;
    latest.current = [...value];
    emitted.current = [...value];
    setDraft([...value]);
  }, [value[0], value[1]]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const emit = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    if (latest.current.every((item, index) => item === emitted.current[index])) return;
    emitted.current = [...latest.current];
    callback.current([...latest.current]);
  };
  const apply = (next: [number, number], immediate = false) => {
    latest.current = next;
    setDraft(next);
    // Keep pointer feedback local while limiting expensive consumer renders.
    if (immediate) emit();
    else if (!timer.current) timer.current = setTimeout(emit, 48);
  };
  const update = (index: 0 | 1, requested: number, immediate = false) => {
    const snapped = Number((min + Math.round((requested - min) / step) * step).toFixed(10));
    const current = latest.current;
    const next: [number, number] = [...current];
    next[index] = index === 0 ? Math.max(min, Math.min(current[1] - gap, snapped))
      : Math.min(max, Math.max(current[0] + gap, snapped));
    apply(next, immediate);
  };
  const moveSelection = (requestedStart: number, original: [number, number], immediate = false) => {
    const duration = original[1] - original[0];
    const start = Math.max(min, Math.min(max - duration, requestedStart));
    apply([Number(start.toFixed(10)), Number((start + duration).toFixed(10))], immediate);
  };
  const pointerValue = (clientX: number) => {
    const rect = track.current!.getBoundingClientRect();
    return min + (clientX - rect.left) / rect.width * (max - min);
  };
  const down = (event: PointerEvent<HTMLDivElement>) => {
    if (unavailable || event.button !== 0 || drag.current) return;
    const target = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-range-handle]");
    const selection = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-range-selection]");
    const position = pointerValue(event.clientX);
    if (variant === "timeline" && !target) {
      if (!selection) return;
      drag.current = { pointer: event.pointerId, kind: "selection", origin: position, value: [...latest.current] };
      setDragging("selection");
      event.preventDefault();
      selection.focus({ preventScroll: true });
      event.currentTarget.setPointerCapture(event.pointerId);
      return;
    }
    // Overlapping hit areas must not let the later DOM handle steal the earlier one.
    const index: 0 | 1 = Math.abs(position - latest.current[0]) < Math.abs(position - latest.current[1]) ? 0 : 1;
    const rect = track.current!.getBoundingClientRect();
    const center = rect.left + (latest.current[index] - min) / (max - min) * rect.width;
    drag.current = { pointer: event.pointerId, kind: "edge", index, offset: target ? event.clientX - center : 0 };
    setDragging("edge");
    event.preventDefault();
    handles.current[index]?.focus({ preventScroll: true });
    event.currentTarget.setPointerCapture(event.pointerId);
    if (!target) update(index, position);
  };
  const move = (event: PointerEvent<HTMLDivElement>) => {
    const active = drag.current;
    if (active?.pointer !== event.pointerId) return;
    if (active.kind === "edge") update(active.index, pointerValue(event.clientX - active.offset));
    else {
      const delta = Math.round((pointerValue(event.clientX) - active.origin) / step) * step;
      moveSelection(active.value[0] + delta, active.value);
    }
  };
  const finish = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current?.pointer !== event.pointerId) return;
    drag.current = null;
    setDragging(null);
    emit();
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const selectionKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    const current = latest.current;
    const values: Record<string, number> = {
      ArrowLeft: current[0] - step, ArrowDown: current[0] - step,
      ArrowRight: current[0] + step, ArrowUp: current[0] + step,
      PageDown: current[0] - step * 10, PageUp: current[0] + step * 10,
      Home: min, End: max - (current[1] - current[0]),
    };
    if (!(event.key in values) || unavailable) return;
    event.preventDefault();
    moveSelection(values[event.key], current, true);
  };
  const key = (event: KeyboardEvent<HTMLButtonElement>, index: 0 | 1) => {
    const current = latest.current[index];
    const values: Record<string, number> = {
      ArrowLeft: current - step, ArrowDown: current - step,
      ArrowRight: current + step, ArrowUp: current + step,
      PageDown: current - step * 10, PageUp: current + step * 10, Home: min, End: max,
    };
    if (!(event.key in values) || unavailable) return;
    event.preventDefault();
    update(index, values[event.key], true);
  };
  const percent = (position: number) => max > min ? Math.max(0, Math.min(100, (position - min) / (max - min) * 100)) : 0;
  const duration = Number((draft[1] - draft[0]).toFixed(10));
  return <div className="sm-range-slider" data-variant={variant} data-dragging={dragging ?? undefined} data-disabled={unavailable || undefined}>
    {variant === "timeline" && <div className="sm-range-slider-ruler" aria-hidden="true">
      {[0, 1, 2, 3, 4].map(tick => <span key={tick} style={{ left: `${tick * 25}%` }}>{formatValue(Number((min + (max - min) * tick / 4).toFixed(2)))}</span>)}
    </div>}
    <div className="sm-range-slider-input" onPointerDown={down} onPointerMove={move}
      onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={finish}>
      <div ref={track} className="sm-range-slider-track">
        {variant === "timeline" ? <button type="button" role="slider" data-range-selection
          className="sm-range-slider-selection" disabled={unavailable}
          style={{ left: `${percent(draft[0])}%`, width: `${percent(draft[1]) - percent(draft[0])}%` }}
          aria-label={selectionLabel} aria-orientation="horizontal" aria-valuenow={draft[0]}
          aria-valuemin={min} aria-valuemax={max - duration}
          aria-valuetext={`${formatValue(draft[0])} – ${formatValue(draft[1])} · ${formatValue(duration)}`}
          onKeyDown={selectionKey}><span>{formatValue(duration)}</span></button> :
          <span className="sm-range-slider-selection" style={{ left: `${percent(draft[0])}%`, width: `${percent(draft[1]) - percent(draft[0])}%` }} />}
        {([0, 1] as const).map((index) => <button key={index} type="button" role="slider"
          ref={(element) => { handles.current[index] = element; }} data-range-handle={index}
          className="sm-range-slider-handle" style={{ left: `${percent(draft[index])}%` }}
          disabled={unavailable} aria-label={index === 0 ? startLabel : endLabel}
          aria-orientation="horizontal" aria-valuenow={draft[index]} aria-valuetext={formatValue(draft[index])}
          aria-valuemin={index === 0 ? min : draft[0] + gap} aria-valuemax={index === 0 ? draft[1] - gap : max}
          onKeyDown={(event) => key(event, index)} />)}
      </div>
    </div>
    <div className="sm-range-slider-values">{variant !== "timeline" && <span>{formatValue(min)}</span>}
      <output>{formatValue(draft[0])} – {formatValue(draft[1])} · {formatValue(duration)}</output>
      {variant !== "timeline" && <span>{formatValue(max)}</span>}</div>
  </div>;
}
