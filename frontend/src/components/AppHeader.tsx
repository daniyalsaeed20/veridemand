import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import { AppBar, Box, Stack, Toolbar, Typography } from "@mui/material";

export function AppHeader() {
  return (
    <AppBar position="static" color="primary" elevation={0}>
      <Toolbar>
        <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
          <DescriptionOutlinedIcon fontSize="large" aria-hidden />
          <Box>
            <Typography variant="h1" component="h1" sx={{ fontSize: "1.4rem", lineHeight: 1.1 }}>
              VeriDemand
            </Typography>
            <Typography variant="subtitle1" sx={{ opacity: 0.85 }}>
              Document Extraction Platform
            </Typography>
          </Box>
        </Stack>
      </Toolbar>
    </AppBar>
  );
}
