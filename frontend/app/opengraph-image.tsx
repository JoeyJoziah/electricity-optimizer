import { ImageResponse } from "next/og";

export const alt = "RateShift - AI-powered utility savings";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OGImage() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background:
          "linear-gradient(135deg, #1e40af 0%, #2563eb 50%, #3b82f6 100%)",
        fontFamily: "sans-serif",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "16px",
          marginBottom: "24px",
        }}
      >
        <svg
          width="64"
          height="64"
          viewBox="0 0 24 24"
          fill="none"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M13 2L3 14h9l-1 10 10-12h-9l1-10z" />
        </svg>
        <div
          style={{
            fontSize: "72px",
            fontWeight: 700,
            color: "white",
            letterSpacing: "-2px",
          }}
        >
          RateShift
        </div>
      </div>
      <div
        style={{
          fontSize: "28px",
          color: "rgba(255, 255, 255, 0.85)",
          fontWeight: 400,
        }}
      >
        AI-Powered Utility Savings for All 50 States
      </div>
    </div>,
    { ...size },
  );
}
