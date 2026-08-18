import { start } from "workflow/api";

import { refreshBluesky } from "@/workflows/refresh-bluesky";

export async function GET(request: Request) {
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`) {
    return new Response("Unauthorized", { status: 401 });
  }

  const run = await start(refreshBluesky);
  return Response.json({ runId: run.runId }, { status: 202 });
}
