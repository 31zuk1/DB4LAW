import { NextRequest, NextResponse } from "next/server";
import { getDocumentById } from "@/lib/vault-index";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const id = request.nextUrl.searchParams.get("id");
  if (!id) {
    return NextResponse.json(
      { error: "id query is required" },
      { status: 400 },
    );
  }

  try {
    const doc = await getDocumentById(id);
    if (!doc) {
      return NextResponse.json(
        { error: "Document not found" },
        { status: 404 },
      );
    }
    return NextResponse.json({ doc });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error ? error.message : "Failed to load document",
      },
      { status: 500 },
    );
  }
}
