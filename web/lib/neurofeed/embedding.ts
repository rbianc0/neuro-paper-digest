import "server-only";

import { createSupabaseServiceClient } from "@/lib/supabase/service";
import { NEUROFEED, normalizeText, sha256, vectorLiteral } from "./core";

async function embed(text: string) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error("OPENAI_API_KEY is required");

  const response = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: NEUROFEED.embeddingModel,
      input: text,
      dimensions: NEUROFEED.embeddingDimensions,
      encoding_format: "float",
    }),
  });

  if (!response.ok) {
    throw new Error(`OpenAI embeddings failed (${response.status}): ${(await response.text()).slice(0, 400)}`);
  }

  const body = await response.json() as { data?: Array<{ embedding?: number[] }> };
  const vector = body.data?.[0]?.embedding;
  if (!vector || vector.length !== NEUROFEED.embeddingDimensions) {
    throw new Error("OpenAI returned an invalid embedding");
  }
  return vector;
}

export async function embedUserProfile(userId: string) {
  const db = createSupabaseServiceClient();
  const { data: profile, error: profileError } = await db
    .from("profiles")
    .select("research_description")
    .eq("user_id", userId)
    .single();
  if (profileError) throw profileError;

  const text = normalizeText(profile.research_description);
  if (!text) throw new Error("Research description is empty");

  const inputHash = sha256(text);
  const { data: current, error: currentError } = await db
    .from("user_embeddings")
    .select("declared_input_hash,embedding_model")
    .eq("user_id", userId)
    .maybeSingle();
  if (currentError) throw currentError;

  if (
    current?.declared_input_hash === inputHash &&
    current?.embedding_model === NEUROFEED.embeddingModel
  ) {
    return { changed: false };
  }

  const vector = await embed(text);
  const { error } = await db.from("user_embeddings").upsert({
    user_id: userId,
    declared_embedding: vectorLiteral(vector),
    declared_input_hash: inputHash,
    embedding_model: NEUROFEED.embeddingModel,
  }, { onConflict: "user_id" });
  if (error) throw error;

  return { changed: true };
}
