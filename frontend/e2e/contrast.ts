import type { Locator } from "@playwright/test";

/** Measures painted CSS colors, including alpha and the endpoints of linear gradients.
 * Media, filters, shadows, text antialiasing and screen-reader behavior need separate review.
 * Samples must have an opaque control/panel ancestor, so backdrop images are not guessed.
 */
export async function textContrast(locator: Locator, translucentSurface?: { selector: string; pseudo: string }) {
  await locator.evaluate(async element => {
    const transitions: Animation[] = [];
    for (let node: Element | null = element; node; node = node.parentElement) {
      transitions.push(...node.getAnimations().filter(animation => Number.isFinite(animation.effect?.getTiming().iterations ?? 1)));
    }
    await Promise.all(transitions.map(animation => animation.finished.catch(() => undefined)));
  });
  return locator.evaluate((element, translucentSurface) => {
    type Color = [number, number, number, number];
    const canvas = document.createElement("canvas").getContext("2d")!;
    const rgba = (value: string): Color => {
      if (!CSS.supports("color", value)) throw new Error(`Unsupported color: ${value}`);
      canvas.clearRect(0, 0, 1, 1);
      canvas.fillStyle = value;
      canvas.fillRect(0, 0, 1, 1);
      return [...canvas.getImageData(0, 0, 1, 1).data].map((v, i) => i === 3 ? v / 255 : v) as Color;
    };
    const over = (fg: Color, bg: Color): Color => fg.slice(0, 3).map((v, i) => v * fg[3] + bg[i] * (1 - fg[3])).concat(1) as Color;
    const stops = (image: string): Color[] => {
      if (image === "none") return [];
      if (!image.startsWith("linear-gradient(")) throw new Error(`Unsupported background: ${image}`);
      const source = image.slice(16, -1);
      const parts: string[] = [];
      let depth = 0, start = 0;
      for (let i = 0; i < source.length; i++) {
        if (source[i] === "(") depth++;
        if (source[i] === ")") depth--;
        if (source[i] === "," && depth === 0) { parts.push(source.slice(start, i).trim()); start = i + 1; }
      }
      parts.push(source.slice(start).trim());
      if (!CSS.supports("color", parts[0])) parts.shift(); // optional direction
      return parts.map(part => rgba(part.replace(/\s+[-\d.]+%$/, "")));
    };
    const backgrounds = (node: Element | null): Color[] => {
      if (!node) throw new Error("No opaque surface behind contrast sample");
      // For frosted media overlays, test the entire black-to-white backdrop range.
      // Blur/saturation cannot exceed these luminance extrema; do not assume the poster is pale.
      if (translucentSurface && node.matches(translucentSurface.selector)) {
        const surface = getComputedStyle(node, translucentSurface.pseudo);
        const layers = stops(surface.backgroundImage);
        if (!layers.length) throw new Error("Missing translucent surface gradient");
        return layers.flatMap(color => [[0, 0, 0, 1], [255, 255, 255, 1]].map(bg => over(color, bg as Color)));
      }
      const style = getComputedStyle(node);
      if (Number(style.opacity) !== 1 && (node !== element || style.backgroundImage !== "none" || rgba(style.backgroundColor)[3] !== 0)) {
        throw new Error("Group opacity needs separate compositing review");
      }
      const gradient = stops(style.backgroundImage);
      if (gradient.length && gradient.every(color => color[3] === 1)) return gradient;
      const fill = rgba(style.backgroundColor);
      const below = fill[3] === 1 ? [fill] : backgrounds(node.parentElement).map(color => over(fill, color));
      return gradient.length ? gradient.flatMap(color => below.map(bg => over(color, bg))) : below;
    };
    const luminance = (color: Color) => color.slice(0, 3).map(value => {
      const channel = value / 255;
      return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
    }).reduce((sum, value, i) => sum + value * [.2126, .7152, .0722][i], 0);
    const style = getComputedStyle(element);
    const foreground = rgba(style.color);
    // A transparent text-only leaf composites its opacity directly into the glyph color.
    foreground[3] *= Number(style.opacity);
    const samples = backgrounds(element);
    const ratios = samples.map(background => {
      const values = [luminance(over(foreground, background)), luminance(background)].sort((a, b) => b - a);
      return (values[0] + .05) / (values[1] + .05);
    });
    return { text: element.textContent?.trim(), foreground, backgrounds: samples, minimumRatio: Math.min(...ratios) };
  }, translucentSurface);
}
