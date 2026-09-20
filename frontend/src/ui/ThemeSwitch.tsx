import { Moon, Sun } from "lucide-react";
import { SegmentedControl } from "terry-react-ui-library";
import { setColorTheme, useColorTheme } from "./theme";

export function ThemeSwitch() {
  const theme = useColorTheme();
  return (
    <div className="theme-switch">
      <SegmentedControl
        fluid
        compact
        ariaLabel="界面主题"
        value={theme}
        onChange={setColorTheme}
        options={[
          { value: "light" as const, label: <Sun size={15} aria-label="亮色" /> },
          { value: "dark" as const, label: <Moon size={15} aria-label="暗色" /> },
        ]}
      />
    </div>
  );
}
