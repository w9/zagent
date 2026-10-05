// OKLCH to sRGB and WCAG 2 contrast. Matrices from https://bottosson.github.io/posts/oklab/.
export type Rgb = [number, number, number]

export function oklchToLinearRgb(lightness: number, chroma: number, hue: number): Rgb {
  const radians = (hue * Math.PI) / 180
  const a = chroma * Math.cos(radians)
  const b = chroma * Math.sin(radians)
  const l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ]
}

export function inGamut(rgb: Rgb): boolean {
  return rgb.every((channel) => channel >= -0.001 && channel <= 1.001)
}

export function luminance(rgb: Rgb): number {
  const [r, g, b] = rgb.map((channel) => Math.min(1, Math.max(0, channel)))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrast(first: Rgb, second: Rgb): number {
  const [light, dark] = [luminance(first), luminance(second)].sort((x, y) => y - x)
  return (light + 0.05) / (dark + 0.05)
}

export function parseOklch(value: string): { rgb: Rgb; alpha: number } | null {
  const match = value.trim().match(/^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*(?:\/\s*([\d.]+))?\s*\)$/)
  if (!match) return null
  const [lightness, chroma, hue, alpha] = match.slice(1).map((part) => (part === undefined ? 1 : Number(part)))
  return { rgb: oklchToLinearRgb(lightness, chroma, hue), alpha }
}
