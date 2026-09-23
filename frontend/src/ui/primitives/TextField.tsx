import { useEffect, useRef, useState } from "react";
import { ResetButton } from "./ResetButton";
import { Tooltip } from "./Tooltip";

export type TextFieldProps = {
  value: string;
  rawValue?: string;
  onChange: (value: string) => void;
  placeholder?: string;
  tooltip?: string;
  disabled?: boolean;
};

// Text editing must stay native-speed even when the consumer renders a very large table.
// The visible input is local; the parent receives a trailing coalesced value, with blur
// committing immediately. This delay never applies to what the user sees or types.
const COMMIT_DELAY_MS = 120;

export function TextField({ value, rawValue, onChange, placeholder, tooltip, disabled }: TextFieldProps) {
  const [draftValue, setDraftValue] = useState(value);
  const latestValue = useRef(value);
  const lastEmittedValue = useRef(value);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onChangeRef = useRef(onChange);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    const hasNewerLocalDraft = latestValue.current !== lastEmittedValue.current;
    if (hasNewerLocalDraft && value === lastEmittedValue.current) return;
    setDraftValue(value);
    latestValue.current = value;
    lastEmittedValue.current = value;
  }, [value]);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const emitLatest = () => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    const next = latestValue.current;
    if (next === lastEmittedValue.current) return;
    lastEmittedValue.current = next;
    onChangeRef.current(next);
  };

  const scheduleEmit = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(emitLatest, COMMIT_DELAY_MS);
  };

  const updateDraft = (next: string) => {
    latestValue.current = next;
    setDraftValue(next);
    scheduleEmit();
  };

  const changed = rawValue !== undefined && draftValue !== rawValue;
  return <div className="tc-control-wrap"><Tooltip text={tooltip}><div className="tc-control tc-text"><input value={draftValue} disabled={disabled} placeholder={placeholder} onChange={event => updateDraft(event.target.value)} onBlur={emitLatest}/></div></Tooltip>{rawValue !== undefined && <ResetButton visible={changed} onClick={() => { latestValue.current = rawValue; setDraftValue(rawValue); emitLatest(); }}/>}</div>;
}
