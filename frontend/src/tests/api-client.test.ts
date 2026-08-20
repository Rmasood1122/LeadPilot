/**
 * API client tests (Chunk 7) — normalizeError handles every FastAPI error
 * shape the backend produces: string detail, validation array, and plain
 * HTTP errors with non-JSON bodies.
 */

import { describe, it, expect, vi } from "vitest";
import { normalizeError, ApiError } from "@/lib/api/client";

function makeResp(status: number, body: unknown, contentType = "application/json"): Response {
  const text =
    typeof body === "string" ? body : JSON.stringify(body);
  return new Response(text, {
    status,
    headers: { "Content-Type": contentType },
  });
}

describe("normalizeError", () => {
  it("extracts string detail from FastAPI error", async () => {
    const err = await normalizeError(
      makeResp(401, { detail: "invalid email or password" }),
    );
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(401);
    expect(err.detail).toBe("invalid email or password");
  });

  it("joins pydantic validation array into human string", async () => {
    const err = await normalizeError(
      makeResp(422, {
        detail: [
          { loc: ["body", "email"], msg: "value is not a valid email address" },
          { loc: ["body", "password"], msg: "ensure this value has at least 8 characters" },
        ],
      }),
    );
    expect(err.status).toBe(422);
    expect(err.detail).toContain("email");
    expect(err.detail).toContain("password");
  });

  it("falls back to status line for non-JSON bodies", async () => {
    const err = await normalizeError(
      makeResp(503, "Service Unavailable", "text/plain"),
    );
    expect(err.status).toBe(503);
    expect(err.detail).toContain("503");
  });

  it("handles empty body gracefully", async () => {
    const err = await normalizeError(new Response("", { status: 500 }));
    expect(err.status).toBe(500);
    expect(typeof err.detail).toBe("string");
  });

  it("handles detail as unknown object gracefully", async () => {
    const err = await normalizeError(
      makeResp(400, { detail: { nested: "unexpected" } }),
    );
    // Should not throw — falls back to status line
    expect(err.status).toBe(400);
    expect(typeof err.detail).toBe("string");
  });
});
