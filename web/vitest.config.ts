import { defineConfig, mergeConfig } from "vitest/config";

import viteConfig from "./vite.config.ts";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      coverage: {
        provider: "v8",
        include: ["src/**"],
        // shadcn primitives are vendored, and main.tsx only mounts the app.
        exclude: ["src/components/ui/**", "src/test/**", "src/main.tsx", "**/*.test.*"],
        reporter: ["text-summary", "text"],
        // Just under what was measured, so coverage cannot fall silently.
        // Raise these as tests are added; never lower them to pass a build.
        thresholds: { statements: 72, branches: 66, functions: 62, lines: 75 },
      },
    },
  }),
);
