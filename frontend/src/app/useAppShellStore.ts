import { create } from "zustand";

// Ephemeral UI shell state only. Never used for backend data and never
// persisted (no localStorage / IndexedDB / cookies / service-worker caches).
interface AppShellState {
  mobileNavOpen: boolean;
  diagnosticsExpanded: boolean;
  setMobileNavOpen: (open: boolean) => void;
  toggleDiagnostics: () => void;
}

export const useAppShellStore = create<AppShellState>((set) => ({
  mobileNavOpen: false,
  diagnosticsExpanded: false,
  setMobileNavOpen: (open) => set({ mobileNavOpen: open }),
  toggleDiagnostics: () => set((state) => ({ diagnosticsExpanded: !state.diagnosticsExpanded })),
}));
