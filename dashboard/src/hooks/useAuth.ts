"use client";

import { useAuthStore } from "@/stores/authStore";

export function useAuth() {
  const { officer, accessToken, isAuthenticated, login, logout } =
    useAuthStore();

  return {
    officer,
    accessToken,
    isAuthenticated,
    login,
    logout,
  };
}
