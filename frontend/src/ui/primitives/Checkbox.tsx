import { Check } from "lucide-react";

export type CheckboxProps = {
  variant?: "default" | "media";
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  title?: string;
  ariaLabel?: string;
  className?: string;
};

export function Checkbox({ variant = "default", checked, onChange, disabled = false, title, ariaLabel, className = "" }: CheckboxProps) {
  return <label className={`tc-checkbox ${variant === "media" ? "tc-checkbox-media" : ""} ${className}`.trim()} title={title}>
    <input
      type="checkbox"
      checked={checked}
      disabled={disabled}
      aria-label={ariaLabel}
      onChange={event => onChange(event.target.checked)}
    />
    <span className="tc-check-box" aria-hidden="true">{checked && <Check size={variant === "media" ? 14.4 : 13}/>}</span>
  </label>;
}
