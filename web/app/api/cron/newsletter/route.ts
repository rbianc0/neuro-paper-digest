import { start } from "workflow/api";

import { sendWeeklyDigests } from "@/workflows/send-weekly-digests";

export async function GET(request: Request) {
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`) {
    return new Response("Unauthorized", { status: 401 });
  }

  const run = await start(sendWeeklyDigests);
  return Response.json({ runId: run.runId }, { status: 202 });
}
