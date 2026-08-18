import "server-only";

import { randomUUID } from "node:crypto";
import nodemailer from "nodemailer";

import { createSupabaseServiceClient } from "@/lib/supabase/service";
import { RankedPaper, sha256, token } from "./core";
import { rankUser } from "./ranking";

const SUMMARY_MODEL = "gpt-5.6-luna";
const INITIAL_VERSION = "initial-v1";

type Paper = {
  paper_id: string;
  title: string;
  abstract: string | null;
  journal: string | null;
  publication_date: string | null;
  first_online_date: string | null;
  canonical_doi: string | null;
  canonical_url: string | null;
  authors: Array<{ name?: string }>;
};

type Narrative = { paperId: string; summary: string; why: string };

function period() {
  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - 6);
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) };
}

function section(item: RankedPaper, rank: number) {
  if (rank < 3) return "Must Read";
  if (item.blueskyScore >= 0.35) return "From Your Bluesky Network";
  if (item.lane === "broad") return "Broader Discovery";
  return "Highly Relevant";
}

async function narratives(papers: Paper[], ranked: RankedPaper[]) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error("OPENAI_API_KEY is required");

  const ranking = new Map(ranked.map((item) => [item.paperId, item]));
  const input = papers.map((paper) => ({
    paperId: paper.paper_id,
    title: paper.title,
    abstract: (paper.abstract || "").slice(0, 5000),
    journal: paper.journal,
    authors: (paper.authors || []).map((author) => author.name).filter(Boolean),
    recommendation: ranking.get(paper.paper_id),
  }));

  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model: SUMMARY_MODEL,
      reasoning: { effort: "max" },
      input: [
        {
          role: "system",
          content: "You write concise neuroscience newsletter copy. Use only the supplied bibliographic metadata and abstract. Do not invent findings, methods, sample sizes, significance, or claims. Explain recommendation reasons from the supplied ranking signals, not from speculation.",
        },
        { role: "user", content: JSON.stringify(input) },
      ],
      text: {
        format: {
          type: "json_schema",
          name: "neurofeed_digest_narratives",
          strict: true,
          schema: {
            type: "object",
            additionalProperties: false,
            required: ["items"],
            properties: {
              items: {
                type: "array",
                items: {
                  type: "object",
                  additionalProperties: false,
                  required: ["paperId", "summary", "why"],
                  properties: {
                    paperId: { type: "string" },
                    summary: { type: "string" },
                    why: { type: "string" },
                  },
                },
              },
            },
          },
        },
      },
    }),
  });
  if (!response.ok) throw new Error(`OpenAI summary failed (${response.status}): ${(await response.text()).slice(0, 500)}`);
  const body = await response.json() as any;
  const outputText = body.output_text || body.output?.flatMap((item: any) => item.content || []).find((part: any) => part.type === "output_text")?.text;
  if (!outputText) throw new Error("OpenAI returned no structured summary output");
  const parsed = JSON.parse(outputText) as { items: Narrative[] };
  return new Map(parsed.items.map((item) => [item.paperId, item]));
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!);
}

function render(displayName: string | null, items: Array<{ paper: Paper; narrative: Narrative; section: string; links: Record<string, string> }>) {
  const groups = ["Must Read", "From Your Bluesky Network", "Highly Relevant", "Broader Discovery"];
  const greeting = displayName ? `Hi ${displayName},` : "Hello,";
  const html: string[] = [
    '<!doctype html><html><body style="font-family:Arial,sans-serif;max-width:760px;margin:0 auto;padding:24px;color:#111;line-height:1.45">',
    '<h1 style="margin-bottom:4px">Neurofeed</h1>',
    `<p>${escapeHtml(greeting)} here is your first personalized Neurofeed.</p>`,
  ];
  const text = ["NEUROFEED", "", greeting, "Here is your first personalized Neurofeed.", ""];

  for (const group of groups) {
    const groupItems = items.filter((item) => item.section === group);
    if (!groupItems.length) continue;
    html.push(`<h2 style="margin-top:30px">${escapeHtml(group)}</h2>`);
    text.push(group.toUpperCase(), "-");
    for (const item of groupItems) {
      const authors = item.paper.authors.map((author) => author.name).filter(Boolean).slice(0, 3).join(", ");
      const meta = [authors, item.paper.journal].filter(Boolean).join(" · ");
      html.push(
        '<div style="margin:0 0 26px;padding:0 0 20px;border-bottom:1px solid #ddd">',
        `<h3 style="margin-bottom:5px"><a href="${escapeHtml(item.links.read)}">${escapeHtml(item.paper.title)}</a></h3>`,
        meta ? `<div style="color:#555;font-size:14px">${escapeHtml(meta)}</div>` : "",
        `<p>${escapeHtml(item.narrative.summary)}</p>`,
        `<p><strong>Why this reached you:</strong> ${escapeHtml(item.narrative.why)}</p>`,
        `<p style="font-size:14px"><a href="${escapeHtml(item.links.read)}">Read paper</a> · <a href="${escapeHtml(item.links.save)}">Save</a> · <a href="${escapeHtml(item.links.more)}">More like this</a> · <a href="${escapeHtml(item.links.less)}">Less like this</a></p>`,
        "</div>",
      );
      text.push(item.paper.title, meta, item.narrative.summary, `Why this reached you: ${item.narrative.why}`, `Read: ${item.links.read}`, `Save: ${item.links.save}`, `More like this: ${item.links.more}`, `Less like this: ${item.links.less}`, "");
    }
  }
  html.push('<p style="margin-top:32px;color:#666;font-size:12px">Neurofeed uses your interests, your Bluesky scientific network and your feedback to rank papers. Following researchers remains on Bluesky.</p></body></html>');
  text.push("Neurofeed uses your interests, your Bluesky scientific network and your feedback to rank papers. Following researchers remains on Bluesky.");
  return { html: html.join(""), text: text.join("\n") };
}

async function interaction(userId: string, paperId: string, digestId: string, action: "CLICK" | "SAVE" | "MORE_LIKE_THIS" | "LESS_LIKE_THIS", redirectUrl: string | null, metadata: Record<string, unknown>) {
  const db = createSupabaseServiceClient();
  const raw = token();
  const { error } = await db.from("interaction_tokens").insert({
    token_hash: sha256(raw),
    user_id: userId,
    paper_id: paperId,
    digest_id: digestId,
    action_type: action,
    redirect_url: redirectUrl,
    expires_at: new Date(Date.now() + 45 * 86_400_000).toISOString(),
    single_use: action !== "CLICK",
    metadata,
  });
  if (error) throw error;
  const base = (process.env.NEXT_PUBLIC_SITE_URL || process.env.NEUROFEED_PUBLIC_URL || "").replace(/\/$/, "");
  if (!base) throw new Error("NEXT_PUBLIC_SITE_URL is required");
  if (action === "CLICK") return `${base}/r/${encodeURIComponent(raw)}`;
  const slug = action === "SAVE" ? "save" : action === "MORE_LIKE_THIS" ? "more" : "less";
  return `${base}/action/${slug}/${encodeURIComponent(raw)}`;
}

export async function createInitialDigest(userId: string) {
  const db = createSupabaseServiceClient();
  const dates = period();
  const { data: existing, error: existingError } = await db
    .from("digests")
    .select("id,status")
    .eq("user_id", userId)
    .eq("period_start", dates.start)
    .eq("period_end", dates.end)
    .eq("version", INITIAL_VERSION)
    .maybeSingle();
  if (existingError) throw existingError;
  if (existing) return existing.id as string;

  const ranked = await rankUser(userId);
  if (!ranked.length) return null;

  const [{ data: profile, error: profileError }, { data: paperRows, error: paperError }] = await Promise.all([
    db.from("profiles").select("display_name").eq("user_id", userId).single(),
    db.rpc("get_digest_paper_data", { p_paper_ids: ranked.map((item) => item.paperId) }),
  ]);
  if (profileError) throw profileError;
  if (paperError) throw paperError;
  const papers = (paperRows || []) as Paper[];
  const paperMap = new Map(papers.map((paper) => [paper.paper_id, paper]));
  const copy = await narratives(papers, ranked);

  const digestId = randomUUID();
  const { error: digestError } = await db.from("digests").insert({
    id: digestId,
    user_id: userId,
    period_start: dates.start,
    period_end: dates.end,
    version: INITIAL_VERSION,
    status: "PREPARING",
  });
  if (digestError) throw digestError;

  try {
    const renderedItems = [];
    for (let index = 0; index < ranked.length; index++) {
      const item = ranked[index];
      const paper = paperMap.get(item.paperId);
      const narrative = copy.get(item.paperId);
      if (!paper || !narrative) continue;
      const itemSection = section(item, index);
      const metadata = { ranking: item, section: itemSection };
      const links = {
        read: await interaction(userId, item.paperId, digestId, "CLICK", paper.canonical_url, metadata),
        save: await interaction(userId, item.paperId, digestId, "SAVE", null, metadata),
        more: await interaction(userId, item.paperId, digestId, "MORE_LIKE_THIS", null, metadata),
        less: await interaction(userId, item.paperId, digestId, "LESS_LIKE_THIS", null, metadata),
      };
      const { error } = await db.from("digest_items").insert({
        digest_id: digestId,
        paper_id: item.paperId,
        rank: index + 1,
        section: itemSection,
        final_score: item.finalScore,
        semantic_score: item.semanticScore,
        bluesky_score: item.blueskyScore,
        fit_score: item.fitScore,
        quality_score: item.qualityScore,
        broad_discovery_score: item.broadScore,
        novelty_score: item.noveltyScore,
        recency_score: item.recencyScore,
        explanation_snapshot: item,
        summary: narrative.summary,
        why_recommended: narrative.why,
        paper_url: paper.canonical_url,
        summary_model: SUMMARY_MODEL,
        summary_input_hash: sha256(`${paper.title}\n${paper.abstract || ""}\n${JSON.stringify(item)}`),
      });
      if (error) throw error;
      renderedItems.push({ paper, narrative, section: itemSection, links });
    }

    const rendered = render(profile.display_name, renderedItems);
    const subject = `Your first Neurofeed — ${renderedItems.length} papers for you`;
    const { error } = await db.from("digests").update({
      subject,
      rendered_html: rendered.html,
      rendered_text: rendered.text,
      content_hash: sha256(`${rendered.html}\n${rendered.text}`),
      status: "GENERATED",
    }).eq("id", digestId);
    if (error) throw error;
    return digestId;
  } catch (error) {
    await db.from("digests").delete().eq("id", digestId);
    throw error;
  }
}

export async function sendDigest(digestId: string) {
  const db = createSupabaseServiceClient();
  const { data: digest, error } = await db
    .from("digests")
    .select("id,user_id,status,subject,rendered_html,rendered_text")
    .eq("id", digestId)
    .single();
  if (error) throw error;
  if (digest.status === "SENT") return { sent: false, alreadySent: true };
  if (digest.status !== "GENERATED") throw new Error(`Digest ${digestId} is not ready to send`);

  const { data: users, error: userError } = await db.rpc("get_newsletter_users");
  if (userError) throw userError;
  const recipient = (users || []).find((row: any) => row.user_id === digest.user_id)?.email;
  if (!recipient) throw new Error("Newsletter recipient email is unavailable");

  const username = process.env.NEUROFEED_SMTP_USERNAME;
  const password = process.env.NEUROFEED_SMTP_PASSWORD;
  const from = process.env.NEUROFEED_EMAIL_FROM;
  if (!username || !password || !from) throw new Error("SMTP configuration is incomplete");

  const { error: claimError } = await db.from("digests").update({ status: "SENDING", delivery_error: null }).eq("id", digestId).eq("status", "GENERATED");
  if (claimError) throw claimError;

  try {
    const transport = nodemailer.createTransport({
      host: "smtp.gmail.com",
      port: 587,
      secure: false,
      auth: { user: username, pass: password },
    });
    const domain = from.match(/@([^>\s]+)>?$/)?.[1] || "neurofeed.local";
    const messageId = `<neurofeed-${digestId}@${domain}>`;
    const result = await transport.sendMail({
      from,
      to: recipient,
      subject: digest.subject || "Neurofeed",
      html: digest.rendered_html || "",
      text: digest.rendered_text || "",
      messageId,
      headers: { "X-Neurofeed-Digest-ID": digestId },
    });

    const { data: items, error: itemError } = await db.from("digest_items").select("paper_id").eq("digest_id", digestId);
    if (itemError) throw itemError;
    if (items?.length) {
      const { error: impressionError } = await db.from("user_paper_events").insert(items.map((item) => ({
        user_id: digest.user_id,
        paper_id: item.paper_id,
        digest_id: digestId,
        event_type: "IMPRESSION",
        metadata: { source: "newsletter_delivery" },
      })));
      if (impressionError) throw impressionError;
    }

    const { error: sentError } = await db.from("digests").update({
      status: "SENT",
      sent_at: new Date().toISOString(),
      delivery_provider: "gmail_smtp",
      delivery_id: result.messageId || messageId,
      delivery_error: null,
    }).eq("id", digestId);
    if (sentError) throw sentError;
    return { sent: true, alreadySent: false };
  } catch (sendError) {
    await db.from("digests").update({ status: "GENERATED", delivery_error: String(sendError).slice(0, 1000) }).eq("id", digestId);
    throw sendError;
  }
}
