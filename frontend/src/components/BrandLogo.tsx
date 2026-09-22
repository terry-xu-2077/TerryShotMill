import type { CSSProperties } from "react";
import mark from "../assets/brand-mark.svg";
import "./BrandLogo.css";

type Props = { size?: number; background?: string; ink?: "black" | "white" };

export function BrandLogo({ size = 40, background, ink }: Props) {
  return <span className="brand-logo" aria-hidden="true" style={{
    width: size, height: size, ...(background ? { backgroundColor: background } : {}),
    ...(ink ? { "--brand-ink": ink } : {}),
  } as CSSProperties}>
    <span className="brand-logo-mark" style={{ maskImage: `url("${mark}")` }} />
  </span>;
}
