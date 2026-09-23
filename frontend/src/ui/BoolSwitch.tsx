import "./BoolSwitch.css";
import type { CSSProperties } from "react";
import { ResetButton } from "./primitives";

export type BoolSwitchProps = {
  value: string;
  rawValue?: string;
  onChange: (value: string) => void;
  trueValue?: string;
  falseValue?: string;
  disabled?: boolean;
  fluid?: boolean;
  width?: number | string;
};

export function BoolSwitch({ value, rawValue, onChange, trueValue = "yes", falseValue = "no", disabled, fluid = false, width }: BoolSwitchProps) {
  const dialectProbe = (value || rawValue || "").trim().toLowerCase();
  const usesLiteralBoolean = dialectProbe === "true" || dialectProbe === "false";
  const effectiveTrue = usesLiteralBoolean ? "true" : trueValue;
  const effectiveFalse = usesLiteralBoolean ? "false" : falseValue;
  const on = value.trim().toLowerCase() === effectiveTrue.toLowerCase();
  const changed = rawValue !== undefined && value !== rawValue;
  const resolvedWidth = width == null ? undefined : (typeof width === "number" ? `${width}px` : width);
  const wrapperStyle = resolvedWidth == null ? undefined : ({ width: resolvedWidth, minWidth: resolvedWidth, maxWidth: resolvedWidth, flexBasis: resolvedWidth } as CSSProperties);

  return <div className={`sm-switch-wrap ${fluid ? "is-fluid" : ""}`} style={wrapperStyle}><button type="button" disabled={disabled} className={`sm-switch ${on ? "is-on" : ""}`} onClick={() => onChange(on ? effectiveFalse : effectiveTrue)} aria-pressed={on}><span className="sm-switch-knob">{on ? "ON" : "OFF"}</span></button>{rawValue !== undefined && <ResetButton visible={changed} onClick={() => onChange(rawValue)}/>}</div>;
}
