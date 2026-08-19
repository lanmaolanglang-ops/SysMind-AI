import { getVersion } from "@tauri-apps/api/app";
import { relaunch } from "@tauri-apps/plugin-process";
import { check } from "@tauri-apps/plugin-updater";

export interface AvailableUpdate {
  version: string;
  notes: string | null;
  install(): Promise<void>;
}

export async function getAppVersion(): Promise<string> {
  return getVersion();
}

export async function checkForAppUpdate(): Promise<AvailableUpdate | null> {
  const update = await check();
  if (!update) return null;

  return {
    version: update.version,
    notes: update.body ?? null,
    install: async () => {
      await update.downloadAndInstall();
      await relaunch();
    },
  };
}
