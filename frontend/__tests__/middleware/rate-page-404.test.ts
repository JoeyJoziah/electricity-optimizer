/**
 * @jest-environment node
 */
import { NextRequest } from "next/server";
import { middleware } from "@/middleware";

function request(path: string) {
  return new NextRequest(new URL(`https://rateshift.app${path}`));
}

describe("middleware: public rate pages", () => {
  it.each([
    "/rates/nonexistent-state/electricity",
    "/rates/connecticut/plutonium",
    "/rates/nonexistent-state/electricity/",
  ])("answers 404 for %s", (path) => {
    const response = middleware(request(path));

    expect(response.status).toBe(404);
    expect(response.headers.get("x-middleware-rewrite")).toMatch(/\/404$/);
    expect(response.headers.get("Content-Security-Policy")).toContain(
      "script-src",
    );
  });

  it.each(["/rates/connecticut/electricity", "/rates/new-york/natural-gas"])(
    "lets %s through",
    (path) => {
      const response = middleware(request(path));

      expect(response.status).toBe(200);
      expect(response.headers.get("x-middleware-rewrite")).toBeNull();
    },
  );
});
