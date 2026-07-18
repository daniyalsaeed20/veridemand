import { create } from "zustand";
import type { CaseSession, Document, UploadRejection } from "../api/client";

export type PendingUpload = {
  id: string;
  displayName: string;
  size: number;
  state: "pending" | "uploading" | "done" | "error";
};

type ShellState = {
  error: string | null;
  session: CaseSession | null;
  documents: Document[];
  rejections: UploadRejection[];
  pending: PendingUpload[];
  expired: boolean;
  setError: (message: string) => void;
  clearError: () => void;
  setSession: (session: CaseSession | null) => void;
  setDocuments: (documents: Document[]) => void;
  addDocuments: (documents: Document[]) => void;
  setRejections: (rejections: UploadRejection[]) => void;
  setPending: (pending: PendingUpload[]) => void;
  setExpired: (expired: boolean) => void;
  removeDocument: (documentId: string) => void;
  resetLocal: () => void;
};

export const useShellStore = create<ShellState>((set) => ({
  error: null,
  session: null,
  documents: [],
  rejections: [],
  pending: [],
  expired: false,
  setError: (message) => set({ error: message }),
  clearError: () => set({ error: null }),
  setSession: (session) => set({ session, expired: false }),
  setDocuments: (documents) => set({ documents }),
  addDocuments: (documents) =>
    set((state) => {
      const byId = new Map(state.documents.map((d) => [d.id, d]));
      for (const doc of documents) {
        byId.set(doc.id, doc);
      }
      return { documents: Array.from(byId.values()) };
    }),
  setRejections: (rejections) => set({ rejections }),
  setPending: (pending) => set({ pending }),
  setExpired: (expired) => set({ expired }),
  removeDocument: (documentId) =>
    set((state) => ({
      documents: state.documents.filter((d) => d.id !== documentId),
    })),
  resetLocal: () =>
    set({
      session: null,
      documents: [],
      rejections: [],
      pending: [],
      expired: false,
      error: null,
    }),
}));
