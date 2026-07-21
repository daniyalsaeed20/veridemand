import { createTheme } from "@mui/material/styles";

// Central application theme. All colours, spacing, radius, typography and
// button behaviour live here so components never hardcode theme values.
export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#1f4e79" },
    secondary: { main: "#4a5568" },
    background: { default: "#f4f6f9", paper: "#ffffff" },
    success: { main: "#2e7d32" },
    warning: { main: "#ed6c02" },
    error: { main: "#c62828" },
  },
  shape: { borderRadius: 10 },
  spacing: 8,
  typography: {
    fontFamily: [
      "system-ui",
      "-apple-system",
      "Segoe UI",
      "Roboto",
      "Helvetica",
      "Arial",
      "sans-serif",
    ].join(", "),
    h1: { fontSize: "1.9rem", fontWeight: 700, letterSpacing: "-0.01em" },
    h2: { fontSize: "1.35rem", fontWeight: 700 },
    h3: { fontSize: "1.1rem", fontWeight: 600 },
    subtitle1: { fontWeight: 500 },
    button: { fontWeight: 600 },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: { root: { textTransform: "none" } },
    },
    MuiPaper: {
      styleOverrides: { root: { backgroundImage: "none" } },
    },
  },
});

// Reusable, semantic status tones mapped to MUI palette colours.
export type StatusTone = "positive" | "caution" | "critical" | "neutral";

export const STATUS_TONE_COLOR: Record<StatusTone, "success" | "warning" | "error" | "default"> = {
  positive: "success",
  caution: "warning",
  critical: "error",
  neutral: "default",
};
