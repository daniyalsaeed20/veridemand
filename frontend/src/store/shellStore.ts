import { create } from "zustand";

type ShellState = {
  error: string | null;
  setError: (message: string) => void;
  clearError: () => void;
};

export const useShellStore = create<ShellState>((set) => ({
  error: null,
  setError: (message) => set({ error: message }),
  clearError: () => set({ error: null }),
}));
