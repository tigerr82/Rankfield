import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Node environment: the units under test are pure logic. Anything touching
    // the DOM is stubbed explicitly by the test that needs it, so the suite
    // stays fast and has no hidden browser dependency.
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
