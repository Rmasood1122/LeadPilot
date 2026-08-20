import type { Config } from "tailwindcss";

/**
 * Every color/radius/spacing token maps to a CSS VARIABLE (section H rule:
 * components never hard-code colors). Presets and the custom builder change
 * the variables; Tailwind classes pick the change up everywhere instantly.
 */
const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "rgb(var(--background) / <alpha-value>)",
        foreground: "rgb(var(--foreground) / <alpha-value>)",
        card: "rgb(var(--card) / <alpha-value>)",
        "card-foreground": "rgb(var(--card-foreground) / <alpha-value>)",
        primary: "rgb(var(--primary) / <alpha-value>)",
        "primary-foreground": "rgb(var(--primary-foreground) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-foreground": "rgb(var(--accent-foreground) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        "muted-foreground": "rgb(var(--muted-foreground) / <alpha-value>)",
        border: "rgb(var(--border) / <alpha-value>)",
        destructive: "rgb(var(--destructive) / <alpha-value>)",
        success: "rgb(var(--success) / <alpha-value>)",
        warning: "rgb(var(--warning) / <alpha-value>)"
      },
      borderRadius: { DEFAULT: "var(--radius)", lg: "calc(var(--radius) + 4px)" },
      fontFamily: { sans: ["var(--font-family)", "system-ui", "sans-serif"] },
      spacing: { gutter: "var(--density-gutter)" }
    }
  },
  plugins: []
};
export default config;
