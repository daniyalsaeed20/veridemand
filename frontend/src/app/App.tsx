import { Box, Container, Stack } from "@mui/material";

import { AppHeader } from "../components/AppHeader";
import { PhaseStatusCard } from "../components/PhaseStatusCard";
import { RuntimeWarning } from "../components/RuntimeWarning";
import { HealthStatusCard } from "../features/health/HealthStatusCard";

export function App() {
  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppHeader />
      <Container maxWidth="md" component="main" sx={{ py: 4 }}>
        <Stack spacing={3}>
          <RuntimeWarning />
          <PhaseStatusCard />
          <HealthStatusCard />
        </Stack>
      </Container>
    </Box>
  );
}
