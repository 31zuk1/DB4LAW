import { NextRequest, NextResponse } from "next/server";

import { getGlobalGraph } from "@/lib/vault-index";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const nodeLimit = Number(
    request.nextUrl.searchParams.get("node_limit") || "360",
  );

  try {
    const graph = await getGlobalGraph(Math.min(Math.max(nodeLimit, 40), 900));
    return NextResponse.json({ graph });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Failed to load global graph",
      },
      { status: 500 },
    );
  }
}
