import type { ButtonHTMLAttributes } from "react";

export type ButtonVariant = "default" | "accent";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: "default" | "icon";
};

export function Button({ children, className = "", variant = "default", size = "default", type = "button", ...props }: ButtonProps) {
  return <button {...props} type={type} className={`tc-button variant-${variant} size-${size} ${className}`.trim()}>{children}</button>;
}
