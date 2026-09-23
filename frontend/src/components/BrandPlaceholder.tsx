import mark from "../assets/brand-mark.svg";
import "./BrandPlaceholder.css";

export function BrandPlaceholder() {
  return <span className="brand-placeholder" aria-hidden="true"><span className="brand-placeholder-disc"><span style={{ maskImage: `url("${mark}")` }} /></span></span>;
}
