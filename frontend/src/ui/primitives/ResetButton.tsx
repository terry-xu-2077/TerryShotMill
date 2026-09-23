import { RotateCcw } from "lucide-react";

export type ResetButtonProps = {
  visible: boolean;
  onClick: () => void;
  label?: string;
};

export function ResetButton({ visible, onClick, label = "还原" }: ResetButtonProps) {
  return <button type="button" className={`tc-reset ${visible ? "is-visible" : ""}`} onClick={onClick} aria-label={label} title={label}><RotateCcw size={14}/></button>;
}
