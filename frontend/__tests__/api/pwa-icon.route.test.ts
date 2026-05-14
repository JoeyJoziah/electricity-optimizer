import { type NextRequest } from "next/server";

// Provide global Response if not available in jsdom
if (typeof global.Response === "undefined") {
  global.Response = class MockResponse {
    status: number;
    body: unknown;
    constructor(body: unknown, init?: { status?: number }) {
      this.body = body;
      this.status = init?.status ?? 200;
    }
  } as unknown as typeof Response;
}

jest.mock("next/og", () => ({
  ImageResponse: jest.fn(
    (element: unknown, options: { width: number; height: number }) => ({
      _element: element,
      _options: options,
      status: 200,
      headers: new Headers(),
    }),
  ),
}));

import { GET } from "@/app/api/pwa-icon/route";

function makeReq(search = "") {
  return {
    nextUrl: {
      searchParams: new URLSearchParams(search),
    },
  } as unknown as NextRequest;
}

describe("GET /api/pwa-icon", () => {
  it("returns a 400 for invalid size", async () => {
    const res = await GET(makeReq("size=256"));
    expect(res.status).toBe(400);
  });

  it("returns a 400 for size=0", async () => {
    const res = await GET(makeReq("size=0"));
    expect(res.status).toBe(400);
  });

  it("returns an ImageResponse for size=192 (default)", async () => {
    const { ImageResponse } = jest.requireMock("next/og");
    (ImageResponse as jest.Mock).mockClear();
    await GET(makeReq("size=192"));
    expect(ImageResponse).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ width: 192, height: 192 }),
    );
  });

  it("returns an ImageResponse for size=512", async () => {
    const { ImageResponse } = jest.requireMock("next/og");
    (ImageResponse as jest.Mock).mockClear();
    await GET(makeReq("size=512"));
    expect(ImageResponse).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ width: 512, height: 512 }),
    );
  });

  it("uses default size 192 when no size param provided", async () => {
    const { ImageResponse } = jest.requireMock("next/og");
    (ImageResponse as jest.Mock).mockClear();
    await GET(makeReq());
    expect(ImageResponse).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ width: 192, height: 192 }),
    );
  });

  it("uses thinner stroke (1.5) for size=512", async () => {
    const { ImageResponse } = jest.requireMock("next/og");
    (ImageResponse as jest.Mock).mockClear();
    await GET(makeReq("size=512"));
    const element = (ImageResponse as jest.Mock).mock.calls[0][0];
    // element is a JSX element; the SVG stroke width should be 1.5
    expect(JSON.stringify(element)).toContain("1.5");
  });

  it("uses wider stroke (2) for size=192", async () => {
    const { ImageResponse } = jest.requireMock("next/og");
    (ImageResponse as jest.Mock).mockClear();
    await GET(makeReq("size=192"));
    const element = (ImageResponse as jest.Mock).mock.calls[0][0];
    expect(JSON.stringify(element)).toContain('"2"');
  });
});
