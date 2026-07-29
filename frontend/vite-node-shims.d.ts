/** Minimal Node ambient types for vite/playwright configs (avoid full @types/node). */

declare module "node:child_process" {
  export interface SpawnSyncReturns {
    status: number | null;
  }

  export function spawnSync(
    command: string,
    args: string[],
    options?: { cwd?: string; stdio?: "inherit" | "pipe" | "ignore" },
  ): SpawnSyncReturns;

  export function execFileSync(
    file: string,
    args?: readonly string[],
    options?: {
      cwd?: string;
      encoding?: BufferEncoding;
      timeout?: number;
      windowsHide?: boolean;
    },
  ): string | Buffer;
}

declare module "node:fs" {
  export function existsSync(path: string): boolean;
}

declare module "node:path" {
  const path: {
    dirname(p: string): string;
    join(...parts: string[]): string;
    resolve(...parts: string[]): string;
  };
  export default path;
}

declare module "node:url" {
  export function fileURLToPath(url: string | URL): string;
}

declare const process: {
  execPath: string;
};

declare const __dirname: string;

interface ImportMeta {
  readonly url: string;
}

type BufferEncoding = "utf8" | "utf-8" | "ascii" | "binary" | "base64" | "hex" | "latin1";

declare const Buffer: {
  from(data: string, encoding?: BufferEncoding): unknown;
};
