"use client";

import { useEffect } from "react";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";

export function ImpressionTracker({ digestId, paperIds }: { digestId: string; paperIds: string[] }) {
  useEffect(() => {
    const key = `neurofeed:impressions:${digestId}`;
    if (window.sessionStorage.getItem(key)) return;
    window.sessionStorage.setItem(key, "1");
    const supabase = createSupabaseBrowserClient();
    void Promise.all(paperIds.map((paperId) => supabase.rpc("record_paper_event", {
      p_paper_id: paperId,
      p_digest_id: digestId,
      p_event_type: "IMPRESSION",
      p_metadata: { surface: "web_latest" },
    })));
  }, [digestId, paperIds]);

  return null;
}
