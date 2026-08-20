/** Theme JSON schema — mirrors the backend ThemeIn Pydantic model exactly. */
export interface Theme {
  preset: string | null;
  background_color: string; // #rrggbb
  background_image_url: string | null;
  background_overlay: number; // 0..0.9 dim strength over bg image
  primary_color: string;
  accent_color: string;
  font_family: string; // Google Fonts family name
  font_size_scale: number; // 0.8..1.4
  radius_px: number; // 0..24
  density: "comfortable" | "compact";
  contrast_warnings: string[];
}

export const DEFAULT_THEME: Theme = {
  preset: "light",
  background_color: "#f8fafc",
  background_image_url: null,
  background_overlay: 0,
  primary_color: "#1d4ed8",
  accent_color: "#0891b2",
  font_family: "Inter",
  font_size_scale: 1,
  radius_px: 8,
  density: "comfortable",
  contrast_warnings: [],
};
