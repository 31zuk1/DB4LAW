import { NextRequest, NextResponse } from "next/server";
import { searchVault } from "@/lib/vault-index";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const query = request.nextUrl.searchParams.get("q") || "";
  const limit = Number(request.nextUrl.searchParams.get("limit") || "100");

  try {
    const payload = await searchVault(query, limit);
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error ? error.message : "Failed to search vault",
      },
      { status: 500 },
    );
  }
}
