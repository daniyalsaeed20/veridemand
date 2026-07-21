import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import ScheduleIcon from "@mui/icons-material/Schedule";
import {
  Card,
  CardContent,
  Chip,
  Divider,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Stack,
  Typography,
} from "@mui/material";

const COMPLETED_CAPABILITIES = [
  "React application shell",
  "FastAPI service",
  "Typed environment configuration",
  "Generated API contracts",
  "Health communication",
];

const UPCOMING_CAPABILITIES = [
  "Upload and queue",
  "Document viewer",
  "Extraction",
  "OCR and handwriting routing",
  "Search and exports",
];

export function PhaseStatusCard() {
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" spacing={2} sx={{ alignItems: "center", mb: 1 }}>
          <Typography variant="h2" component="h2">
            Phase 0 - Repository Foundation and Contracts
          </Typography>
          <Chip label="Foundation ready" color="success" size="small" />
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          This is the platform foundation. The capabilities below are in place; later phases are not
          yet available.
        </Typography>

        <Typography variant="h3" component="h3">
          Available now
        </Typography>
        <List dense>
          {COMPLETED_CAPABILITIES.map((label) => (
            <ListItem key={label} disableGutters>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <CheckCircleOutlineIcon color="success" fontSize="small" />
              </ListItemIcon>
              <ListItemText primary={label} />
            </ListItem>
          ))}
        </List>

        <Divider sx={{ my: 1 }} />

        <Typography variant="h3" component="h3">
          Not yet available
        </Typography>
        <List dense>
          {UPCOMING_CAPABILITIES.map((label) => (
            <ListItem key={label} disableGutters>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <ScheduleIcon color="disabled" fontSize="small" />
              </ListItemIcon>
              <ListItemText
                primary={label}
                secondary="Planned for a later phase"
                slotProps={{ primary: { color: "text.secondary" } }}
              />
            </ListItem>
          ))}
        </List>
      </CardContent>
    </Card>
  );
}
