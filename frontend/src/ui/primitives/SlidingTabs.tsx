import type { CSSProperties } from "react";
import type { SegmentedControlOption } from "./SegmentedControl";

export type SlidingTabsProps<T extends string = string> = {
  value: T;
  options: readonly SegmentedControlOption<T>[];
  onChange: (value: T) => void;
  ariaLabel?: string;
  disabled?: boolean;
  fluid?: boolean;
  compact?: boolean;
  className?: string;
};

/**
 * Borderless compact tabs for dense parameter groups.
 *
 * Visual contract:
 * - No pill shell or rounded item borders.
 * - A muted track stays visible under the whole group.
 * - The accent indicator slides to the selected item.
 * - Selected text uses the shared accent color.
 * - Items share equal width inside the group.
 */
export function SlidingTabs<T extends string = string>({
  value,
  options,
  onChange,
  ariaLabel,
  disabled = false,
  fluid = false,
  compact = false,
  className = "",
}: SlidingTabsProps<T>) {
  const selectedIndex = Math.max(0, options.findIndex((option) => option.value === value));
  const style = {
    "--tc-sliding-count": String(Math.max(1, options.length)),
    "--tc-sliding-index": String(selectedIndex),
  } as CSSProperties;

  return (
    <div
      className={`tc-sliding-tabs ${fluid ? "is-fluid" : ""} ${compact ? "is-compact" : ""} ${className}`.trim()}
      role="tablist"
      aria-label={ariaLabel}
      style={style}
    >
      <span className="tc-sliding-tabs-track" aria-hidden="true" />
      <span className="tc-sliding-tabs-indicator" aria-hidden="true" />
      {options.map((option) => {
        const selected = option.value === value;
        const itemDisabled = disabled || option.disabled === true;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            className={`tc-sliding-tab ${selected ? "is-active" : ""}`}
            aria-selected={selected}
            disabled={itemDisabled}
            onClick={() => onChange(option.value)}
          >
            {option.icon ? <span className="tc-sliding-tab-icon" aria-hidden="true">{option.icon}</span> : null}
            <span className="tc-sliding-tab-label">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}
