import "server-only";

import { createSupabaseServiceClient } from "@/lib/supabase/service";
import { vectorLiteral } from "./core";

type FeedbackRow = {
  effective_weight: number;
  embedding: string | number[];
};

function vector(value: FeedbackRow["embedding"]) {
  if (Array.isArray(value)) return value.map(Number);
  const text = value.trim();
  if (!text.startsWith("[") || !text.endsWith("]")) throw new Error("Invalid pgvector value");
  return text.slice(1, -1).split(",").filter(Boolean).map(Number);
}

function centroid(rows: FeedbackRow[], positive: boolean) {
  const selected = rows.flatMap((row) => {
    const weight = Number(row.effective_weight || 0);
    if (!weight || (weight > 0) !== positive) return [];
    return [{ weight: Math.abs(weight), vector: vector(row.embedding) }];
  });
  if (!selected.length) return null;

  const dimensions = selected[0].vector.length;
  const sum = new Array<number>(dimensions).fill(0);
  let total = 0;
  for (const item of selected) {
    if (item.vector.length !== dimensions) throw new Error("Feedback embeddings have inconsistent dimensions");
    total += item.weight;
    for (let i = 0; i < dimensions; i++) sum[i] += item.weight * item.vector[i];
  }
  return sum.map((value) => value / total);
}

export async function refreshFeedback(userId: string) {
  const db = createSupabaseServiceClient();
  const { data, error } = await db.rpc("get_effective_paper_feedback", {
    p_user_id: userId,
    p_click_weight: 0.25,
    p_save_weight: 1,
    p_more_weight: 1.5,
    p_less_weight: 1.5,
    p_neutral_less_reasons: ["already_knew_it"],
  });
  if (error) throw error;

  const rows = (data || []) as FeedbackRow[];
  const positive = centroid(rows, true);
  const negative = centroid(rows, false);
  const { error: updateError } = await db.from("user_embeddings").update({
    feedback_count: rows.length,
    learned_positive_embedding: positive ? vectorLiteral(positive) : null,
    learned_negative_embedding: negative ? vectorLiteral(negative) : null,
  }).eq("user_id", userId);
  if (updateError) throw updateError;

  return {
    feedbackCount: rows.length,
    positiveCount: rows.filter((row) => Number(row.effective_weight) > 0).length,
    negativeCount: rows.filter((row) => Number(row.effective_weight) < 0).length,
  };
}
