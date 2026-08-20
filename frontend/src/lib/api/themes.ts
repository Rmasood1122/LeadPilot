import { api } from "./client";
import type { Theme } from "@/lib/theme/types";

export async function getTheme(): Promise<Partial<Theme>> {
  const data = await api<{ theme: Partial<Theme> }>("/me/theme");
  return data.theme;
}

export async function saveTheme(theme: Theme): Promise<Theme> {
  const data = await api<{ theme: Theme }>("/me/theme", {
    method: "PUT",
    body: theme,
  });
  return data.theme;
}

export async function uploadBackground(file: File): Promise<string> {
  const formData = new FormData();
  formData.append("file", file);
  const data = await api<{ url: string }>("/me/theme/background", { formData });
  return data.url;
}
