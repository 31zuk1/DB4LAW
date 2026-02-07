import { NextRequest, NextResponse } from "next/server";

import { getGraphById } from "@/lib/vault-index";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const id = request.nextUrl.searchParams.get("id");
  const depth = Number(request.nextUrl.searchParams.get("depth") || "1");
  const nodeLimit = Number(
    request.nextUrl.searchParams.get("node_limit") || "120",
  );

  if (!id) {
    return NextResponse.json(
      { error: "id query is required" },
      { status: 400 },
    );
  }

  try {
    const graph = await getGraphById(
      id,
      Math.min(Math.max(depth, 1), 4),
      Math.min(Math.max(nodeLimit, 10), 240),
    );

    if (!graph) {
      return NextResponse.json(
        { error: "Document not found" },
        { status: 404 },
      );
    }

    return NextResponse.json({ graph });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Failed to load graph",
      },
      { status: 500 },
    );
  }
}
