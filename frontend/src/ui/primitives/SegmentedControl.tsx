import type { ReactNode } from "react";

export type SegmentedControlOption<T extends string = string> = {
  value: T;
  label: ReactNode;
  icon?: ReactNode;
  disabled?: boolean;
};

export type SegmentedControlProps<T extends string = string> = {
  value: T;
  options: readonly SegmentedControlOption<T>[];
  onChange: (value: T) => void;
  ariaLabel?: string;
  disabled?: boolean;
  fluid?: boolean;
  compact?: boolean;
  presentation?: "choice" | "tabs";
  className?: string;
};

/**
 * Equal-width pill segments for high-level mutually-exclusive modes.
 *
 * Visual contract:
 * - Two or more labels read as one pill group.
 * - Every item has equal width.
 * - The outer ends are fully rounded while adjacent internal edges stay square.
 * - The active label uses a slightly brighter surface and accent-colored text.
 * - Products own placement/width, not the internal geometry.
 */
export function SegmentedControl<T extends string = string>({
  value,
  options,
  onChange,
  ariaLabel,
  disabled = false,
  fluid = false,
  compact = false,
  presentation = "choice",
  className = "",
}: SegmentedControlProps<T>) {
  const isTabs = presentation === "tabs";
  return (
    <div
      className={`tc-segmented ${fluid ? "is-fluid" : ""} ${compact ? "is-compact" : ""} ${className}`.trim()}
      role={isTabs ? "tablist" : "group"}
      aria-label={ariaLabel}
    >
      {options.map((option) => {
        const selected = option.value === value;
        const itemDisabled = disabled || option.disabled === true;
        return (
          <button
            key={option.value}
            type="button"
            role={isTabs ? "tab" : undefined}
            className={`tc-segmented-item ${selected ? "is-active" : ""}`}
            aria-selected={isTabs ? selected : undefined}
            aria-pressed={isTabs ? undefined : selected}
            disabled={itemDisabled}
            onClick={() => onChange(option.value)}
          >
            {option.icon ? <span className="tc-segmented-icon" aria-hidden="true">{option.icon}</span> : null}
            <span className="tc-segmented-label">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}
