import { create } from "zustand";
import type { Officer, AuthTokens } from "@/types";

interface AuthState {
  officer: Officer | null;
  tokens: AuthTokens | null;
  isAuthenticated: boolean;
  setAuth: (officer: Officer, tokens: AuthTokens) => void;
  clearAuth: () => void;
  setTokens: (tokens: AuthTokens) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  officer: null,
  tokens: null,
  isAuthenticated: false,
  setAuth: (officer, tokens) =>
    set({ officer, tokens, isAuthenticated: true }),
  clearAuth: () =>
    set({ officer: null, tokens: null, isAuthenticated: false }),
  setTokens: (tokens) => set({ tokens }),
}));
