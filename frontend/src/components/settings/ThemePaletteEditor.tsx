import { useEffect, useState } from "react";
import { Button } from "../../ui/primitives";
import { paletteDefaults, paletteFields, readPalette, savePalette, useColorTheme } from "../../ui/theme";
import "./ThemePaletteEditor.css";

export function ThemePaletteEditor() {
  const mode = useColorTheme();
  const [palette, setPalette] = useState(() => readPalette(mode));
  useEffect(() => {
    const sync = () => setPalette(readPalette(mode));
    sync();
    window.addEventListener("storage", sync);
    window.addEventListener("shotmill-palette-change", sync);
    return () => { window.removeEventListener("storage", sync); window.removeEventListener("shotmill-palette-change", sync); };
  }, [mode]);
  return <div className="theme-palette-editor">
    <strong>{mode === "light" ? "亮色" : "暗色"}模式配色</strong>
    <div className="theme-palette-fields">{paletteFields.map(([key, label]) => <label key={key} className="theme-palette-field">
      <span>{label}</span>
      <input type="color" aria-label={`${label}颜色`} value={palette[key]} onChange={event => {
        const next = { ...palette, [key]: event.target.value }; setPalette(next); savePalette(mode, next);
      }} />
      <input key={`${mode}-${palette[key]}`} className="theme-palette-hex" aria-label={`${label}色值`} defaultValue={palette[key]} maxLength={7}
        onBlur={event => {
          const color = event.target.value.trim();
          if (/^#[0-9a-f]{6}$/i.test(color)) savePalette(mode, { ...palette, [key]: color });
          else event.target.value = palette[key];
        }} onKeyDown={event => { if (event.key === "Enter") event.currentTarget.blur(); }} />
    </label>)}</div>
    <div className="theme-palette-footer"><span>即时生效并自动保存，亮暗配色分别保存。</span>
      <Button onClick={() => savePalette(mode, { ...paletteDefaults[mode] })}>恢复当前模式默认配色</Button>
    </div>
  </div>;
}
