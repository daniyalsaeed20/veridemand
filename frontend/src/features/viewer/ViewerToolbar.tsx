// Toolbar for zoom mode/scale, rotation and the overlay toggle.
//
// Every control is a named, keyboard-operable native element (button/select
// via MUI ToggleButtonGroup and Switch), so the toolbar is fully usable
// without a mouse.

import RotateLeftIcon from "@mui/icons-material/RotateLeft";
import RotateRightIcon from "@mui/icons-material/RotateRight";
import ZoomInIcon from "@mui/icons-material/ZoomIn";
import ZoomOutIcon from "@mui/icons-material/ZoomOut";
import {
  FormControlLabel,
  IconButton,
  Stack,
  Switch,
  Tooltip,
  Typography,
  ToggleButton,
  ToggleButtonGroup,
} from "@mui/material";

import { VIEWER_MAX_SCALE, VIEWER_MIN_SCALE, type ZoomMode } from "./constants";

export interface ViewerToolbarProps {
  readonly zoomMode: ZoomMode;
  readonly effectiveScale: number;
  readonly overlayEnabled: boolean;
  /** When false, the coordinate-test overlay toggle is hidden entirely. */
  readonly showOverlayControls?: boolean;
  readonly overlayDisabledReason?: string | null;
  readonly disabled?: boolean;
  readonly onZoomModeChange: (mode: ZoomMode) => void;
  readonly onZoomIn: () => void;
  readonly onZoomOut: () => void;
  readonly onRotateClockwise: () => void;
  readonly onRotateCounterClockwise: () => void;
  readonly onToggleOverlay: () => void;
}

export function ViewerToolbar({
  zoomMode,
  effectiveScale,
  overlayEnabled,
  showOverlayControls = false,
  overlayDisabledReason = null,
  disabled = false,
  onZoomModeChange,
  onZoomIn,
  onZoomOut,
  onRotateClockwise,
  onRotateCounterClockwise,
  onToggleOverlay,
}: ViewerToolbarProps) {
  const overlayControlDisabled = disabled || Boolean(overlayDisabledReason);
  const scalePercent = Math.round(effectiveScale * 100);

  const overlaySwitch = (
    <FormControlLabel
      control={
        <Switch
          slotProps={{ input: { "aria-label": "Show coordinate-test alignment overlay" } }}
          checked={overlayEnabled && !overlayDisabledReason}
          disabled={overlayControlDisabled}
          onChange={onToggleOverlay}
        />
      }
      label="Coordinate test overlay"
    />
  );

  return (
    <Stack
      direction="row"
      spacing={2}
      sx={{ alignItems: "center", flexWrap: "wrap", gap: 1 }}
      role="toolbar"
      aria-label="Viewer controls"
    >
      <ToggleButtonGroup
        size="small"
        exclusive
        value={zoomMode}
        onChange={(_event, value: ZoomMode | null) => {
          if (value) {
            onZoomModeChange(value);
          }
        }}
        aria-label="Zoom mode"
        disabled={disabled}
      >
        <ToggleButton value="fit_width" aria-label="Fit page width">
          Fit width
        </ToggleButton>
        <ToggleButton value="fit_page" aria-label="Fit whole page">
          Fit page
        </ToggleButton>
        <ToggleButton value="manual" aria-label="Manual zoom">
          Manual
        </ToggleButton>
      </ToggleButtonGroup>

      <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
        <IconButton
          aria-label="Zoom out"
          size="small"
          disabled={disabled || effectiveScale <= VIEWER_MIN_SCALE}
          onClick={onZoomOut}
        >
          <ZoomOutIcon fontSize="small" />
        </IconButton>
        <Typography variant="body2" sx={{ minWidth: 44, textAlign: "center" }} aria-live="polite">
          {scalePercent}%
        </Typography>
        <IconButton
          aria-label="Zoom in"
          size="small"
          disabled={disabled || effectiveScale >= VIEWER_MAX_SCALE}
          onClick={onZoomIn}
        >
          <ZoomInIcon fontSize="small" />
        </IconButton>
      </Stack>

      <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
        <IconButton
          aria-label="Rotate counter-clockwise"
          size="small"
          disabled={disabled}
          onClick={onRotateCounterClockwise}
        >
          <RotateLeftIcon fontSize="small" />
        </IconButton>
        <IconButton
          aria-label="Rotate clockwise"
          size="small"
          disabled={disabled}
          onClick={onRotateClockwise}
        >
          <RotateRightIcon fontSize="small" />
        </IconButton>
      </Stack>

      {showOverlayControls ? (
        overlayDisabledReason ? (
          <Tooltip title={overlayDisabledReason}>
            <span>{overlaySwitch}</span>
          </Tooltip>
        ) : (
          overlaySwitch
        )
      ) : null}
    </Stack>
  );
}
