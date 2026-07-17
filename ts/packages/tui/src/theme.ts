/**
 * Mist visual language — one place for every color the TUI uses.
 *
 * Pastel brand ramp (the wordmark gradient chosen for the Python TUI):
 * Regent St Blue → Powder Blue → Aqua Spring → Melanie → We Peep.
 * Accents keep errors red and success warm-gold for instant scanability.
 */

export const BRAND_RAMP = [
  "#a8d3e1", // regent st blue
  "#b3e4e6", // powder blue
  "#ebf7f9", // aqua spring
  "#e5b8d1", // melanie
  "#f2cad4", // we peep
] as const;

export const theme = {
  brand: "#a8d3e1",
  accent: "#e5b8d1",
  text: "#e8edf7",
  dim: "#8a93a6",
  success: "#df9241", // butterscotch (Cinnamon palette)
  warning: "#d47007", // pumpkin
  error: "#ff6b6b",
  code: "#b3e4e6",
  border: "#5b6478",
  user: "#f2cad4",
} as const;

/** Per-letter gradient color for the brand lockup. */
export function rampColor(i: number, total: number): string {
  if (total <= 1) return BRAND_RAMP[0];
  const t = i / (total - 1);
  const idx = Math.min(BRAND_RAMP.length - 1, Math.round(t * (BRAND_RAMP.length - 1)));
  return BRAND_RAMP[idx] as string;
}

export const HEARTBEAT = ["○", "◔", "◑", "◕", "●", "◕", "◑", "◔"] as const;
export const SPARKLE = ["⡡⠊⢔⠡", "⠊⡰⡡⡘", "⢔⢅⠈⢢", "⡁⢂⠆⡍", "⢔⠨⢑⢐", "⠨⡑⡠⠊"] as const;
