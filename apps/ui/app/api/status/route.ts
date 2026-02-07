import { NextResponse } from "next/server";

import { getVaultStatus } from "@/lib/vault-index";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  try {
    const status = await getVaultStatus();
    return NextResponse.json({ status });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Failed to load status",
      },
      { status: 500 },
    );
  }
}
