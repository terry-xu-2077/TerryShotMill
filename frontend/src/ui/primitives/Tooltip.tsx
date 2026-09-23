import type { ReactNode } from "react";

export type TooltipProps = {
  text?: string;
  children: ReactNode;
};

export function Tooltip({ text, children }: TooltipProps) {
  if (!text) return <>{children}</>;
  return <span className="tc-tooltip-host">{children}<span className="tc-tooltip">{text}</span></span>;
}
