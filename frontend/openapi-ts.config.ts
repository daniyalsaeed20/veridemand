import { defineConfig } from "@hey-api/openapi-ts";

// Generates TypeScript types and Zod v4 runtime schemas from the committed
// OpenAPI document. Never generate from a live server. Generated files are
// committed and must not be edited by hand.
export default defineConfig({
  input: "../docs/contracts/openapi.json",
  output: {
    path: "src/contracts/generated",
    postProcess: [],
  },
  plugins: ["@hey-api/typescript", "zod"],
});
