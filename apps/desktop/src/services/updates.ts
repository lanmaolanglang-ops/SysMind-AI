import { getVersion } from "@tauri-apps/api/app";
import { relaunch } from "@tauri-apps/plugin-process";
import { check } from "@tauri-apps/plugin-updater";

export interface AvailableUpdate {
  version: string;
  notes: string | null;
  /**
   * Installs the update and attempts to relaunch.
   * Resolves `{ relaunched: false }` when install succeeded but restart failed.
   * Rejects only when the install itself failed.
   */
  install(): Promise<{ relaunched: boolean }>;
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
      try {
        await relaunch();
        return { relaunched: true };
      } catch {
        // Install already replaced the binary; only the restart step failed.
        return { relaunched: false };
      }
    },
  };
}
