import { Box, Container, Stack } from "@mui/material";

import { AppHeader } from "../components/AppHeader";
import { RuntimeWarning } from "../components/RuntimeWarning";
import { SessionWorkspace } from "../features/session/SessionWorkspace";

export function App() {
  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppHeader />
      <Container maxWidth="xl" component="main" sx={{ py: 4 }}>
        <Stack spacing={3}>
          <RuntimeWarning />
          <SessionWorkspace />
        </Stack>
      </Container>
    </Box>
  );
}
