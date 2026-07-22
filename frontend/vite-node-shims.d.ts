/** Minimal Node ambient types for vite.config.ts (avoid full @types/node dependency). */

declare module "node:child_process" {
  export interface SpawnSyncReturns {
    status: number | null;
  }

  export function spawnSync(
    command: string,
    args: string[],
    options?: { cwd?: string; stdio?: "inherit" | "pipe" | "ignore" },
  ): SpawnSyncReturns;
}

declare module "node:path" {
  const path: {
    dirname(p: string): string;
    join(...parts: string[]): string;
  };
  export default path;
}

declare module "node:url" {
  export function fileURLToPath(url: string | URL): string;
}

declare const process: {
  execPath: string;
};

interface ImportMeta {
  readonly url: string;
}
