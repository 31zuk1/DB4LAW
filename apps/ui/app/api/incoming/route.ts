import { NextRequest, NextResponse } from "next/server";

import { getIncomingById } from "@/lib/vault-index";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const id = request.nextUrl.searchParams.get("id");
  const limit = Number(request.nextUrl.searchParams.get("limit") || "240");

  if (!id) {
    return NextResponse.json(
      { error: "id query is required" },
      { status: 400 },
    );
  }

  try {
    const incoming = await getIncomingById(
      id,
      Math.min(Math.max(limit, 1), 500),
    );
    return NextResponse.json({ incoming });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Failed to load incoming links",
      },
      { status: 500 },
    );
  }
}
