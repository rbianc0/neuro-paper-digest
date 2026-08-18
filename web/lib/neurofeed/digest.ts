import "server-only";

import { randomUUID } from "node:crypto";
import nodemailer from "nodemailer";

import { createSupabaseServiceClient } from "@/lib/supabase/service";
import { RankedPaper, sha256, token } from "./core";
import { refreshFeedback } from "./feedback";
import { rankUser } from "./ranking";

const SUMMARY_MODEL = "gpt-5.6-luna";
const SECTIONS = ["Must Read", "From Your Bluesky Network", "Highly Relevant", "Broader Discovery"] as const;

type DigestKind = "initial" | "weekly";
type Action = "CLICK" | "SAVE" | "MORE_LIKE_THIS" | "LESS_LIKE_THIS";
type Paper = {
  paper_id: string;
  title: string;
  abstract: string | null;
  journal: string | null;
  canonical_url: string | null;
  authors: Array<{ name?: string }>;
};
type Narrative = { paperId: string; summary: string; why: string };
type RenderedItem = {
  paper: Paper;
  narrative: Narrative;
  section: string;
  links: { read: string; save: string; more: string; less: string };
};

function digestPeriod() {
  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - 6);
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) };
}

function digestVersion(kind: DigestKind) {
  return kind === "initial" ? "initial-v1" : "weekly-v1";
}

function sectionFor(item: RankedPaper, index: number) {
  if (index < 3) return "Must Read";
  if (item.blueskyScore >= 0.35) return "From Your Bluesky Network";
  if (item.lane === "broad") return "Broader Discovery";
  return "Highly Relevant";
}

async function summarize(papers: Paper[], ranked: RankedPaper[]) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error("OPENAI_API_KEY is required");

  const scores = new Map(ranked.map((item) => [item.paperId, item]));
  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model: SUMMARY_MODEL,
      reasoning: { effort: "xhigh" },
      input: [
        {
          role: "system",
          content: "Write concise neuroscience newsletter copy using only the supplied metadata, abstract, and ranking signals. Never invent findings, methods, samples, significance, or claims.",
        },
        {
          role: "user",
          content: JSON.stringify(papers.map((paper) => ({
            paperId: paper.paper_id,
            title: paper.title,
            abstract: (paper.abstract || "").slice(0, 5000),
            journal: paper.journal,
            authors: paper.authors.map((author) => author.name).filter(Boolean),
            recommendation: scores.get(paper.paper_id),
          }))),
        },
      ],
      text: {
        format: {
          type: "json_schema",
          name: "neurofeed_digest",
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

  if (!response.ok) {
    throw new Error(`OpenAI summary failed (${response.status}): ${(await response.text()).slice(0, 500)}`);
  }
  const body = await response.json() as {
    output_text?: string;
    output?: Array<{ content?: Array<{ type?: string; text?: string }> }>;
  };
  const text = body.output_text || body.output?.flatMap((item) => item.content || []).find((part) => part.type === "output_text")?.text;
  if (!text) throw new Error("OpenAI returned no structured summary output");

  const parsed = JSON.parse(text) as { items?: Narrative[] };
  const narratives = new Map((parsed.items || []).map((item) => [item.paperId, item]));
  for (const paper of papers) {
    if (!narratives.has(paper.paper_id)) throw new Error(`Summary missing for paper ${paper.paper_id}`);
  }
  return narratives;
}

function escapeHtml(value: string) {
  const chars: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return value.replace(/[&<>"']/g, (char) => chars[char]);
}

function render(kind: DigestKind, displayName: string | null, items: RenderedItem[]) {
  const greeting = displayName ? `Hi ${displayName},` : "Hello,";
  const intro = kind === "initial" ? "Here is your first personalized Neurofeed." : "Here are this week's papers selected for you.";
  const title = kind === "initial" ? "Neurofeed" : "Neurofeed Weekly";
  const html = [
    '<!doctype html><html><body style="font-family:Arial,sans-serif;max-width:760px;margin:0 auto;padding:24px;color:#111;line-height:1.45">',
    `<h1>${title}</h1><p>${escapeHtml(greeting)} ${escapeHtml(intro)}</p>`,
  ];
  const text = [title.toUpperCase(), "", greeting, intro, ""];

  for (const section of SECTIONS) {
    const sectionItems = items.filter((item) => item.section === section);
    if (!sectionItems.length) continue;
    html.push(`<h2 style="margin-top:30px">${escapeHtml(section)}</h2>`);
    text.push(section.toUpperCase(), "-");

    for (const item of sectionItems) {
      const authors = item.paper.authors.map((author) => author.name).filter(Boolean).slice(0, 3).join(", ");
      const meta = [authors, item.paper.journal].filter(Boolean).join(" · ");
      html.push(
        '<div style="margin-bottom:26px;padding-bottom:20px;border-bottom:1px solid #ddd">',
        `<h3><a href="${escapeHtml(item.links.read)}">${escapeHtml(item.paper.title)}</a></h3>`,
        meta ? `<div style="color:#555;font-size:14px">${escapeHtml(meta)}</div>` : "",
        `<p>${escapeHtml(item.narrative.summary)}</p>`,
        `<p><strong>Why this reached you:</strong> ${escapeHtml(item.narrative.why)}</p>`,
        `<p style="font-size:14px"><a href="${escapeHtml(item.links.read)}">Read paper</a> · <a href="${escapeHtml(item.links.save)}">Save</a> · <a href="${escapeHtml(item.links.more)}">More like this</a> · <a href="${escapeHtml(item.links.less)}">Less like this</a></p>`,
        "</div>",
      );
      text.push(
        item.paper.title,
        meta,
        item.narrative.summary,
        `Why this reached you: ${item.narrative.why}`,
        `Read: ${item.links.read}`,
        `Save: ${item.links.save}`,
        `More like this: ${item.links.more}`,
        `Less like this: ${item.links.less}`,
        "",
      );
    }
  }

  const footer = "Neurofeed uses your interests, your Bluesky scientific network and your feedback to rank papers. Following researchers remains on Bluesky.";
  html.push(`<p style="margin-top:32px;color:#666;font-size:12px">${footer}</p></body></html>`);
  text.push(footer);
  return { html: html.join(""), text: text.join("\n") };
}

function link(base: string, action: Action, raw: string) {
  if (action === "CLICK") return `${base}/r/${encodeURIComponent(raw)}`;
  const slug = action === "SAVE" ? "save" : action === "MORE_LIKE_THIS" ? "more" : "less";
  return `${base}/action/${slug}/${encodeURIComponent(raw)}`;
}

async function createDigest(userId: string, kind: DigestKind) {
  const db = createSupabaseServiceClient();
  const dates = digestPeriod();
  const version = digestVersion(kind);

  const { data: existing, error: existingError } = await db
    .from("digests")
    .select("id,status")
    .eq("user_id", userId)
    .eq("period_start", dates.start)
    .eq("period_end", dates.end)
    .eq("version", version)
    .maybeSingle();
  if (existingError) throw existingError;
  if (existing && ["GENERATED", "SENDING", "SENT"].includes(existing.status)) return existing.id as string;
  if (existing) {
    const { error } = await db.from("digests").delete().eq("id", existing.id);
    if (error) throw error;
  }

  if (kind === "weekly") await refreshFeedback(userId);
  const ranked = await rankUser(userId);
  if (!ranked.length) return null;

  const [{ data: profile, error: profileError }, { data: paperRows, error: paperError }] = await Promise.all([
    db.from("profiles").select("display_name,newsletter_enabled").eq("user_id", userId).single(),
    db.rpc("get_digest_paper_data", { p_paper_ids: ranked.map((item) => item.paperId) }),
  ]);
  if (profileError) throw profileError;
  if (paperError) throw paperError;
  if (!profile.newsletter_enabled) return null;

  const paperMap = new Map(((paperRows || []) as Paper[]).map((paper) => [paper.paper_id, paper]));
  const orderedPapers = ranked
    .map((item) => paperMap.get(item.paperId))
    .filter((paper): paper is Paper => Boolean(paper?.canonical_url));
  if (!orderedPapers.length) return null;

  const narratives = await summarize(orderedPapers, ranked);
  const digestId = randomUUID();
  const { error: digestError } = await db.from("digests").insert({
    id: digestId,
    user_id: userId,
    period_start: dates.start,
    period_end: dates.end,
    version,
    status: "PREPARING",
  });
  if (digestError) throw digestError;

  try {
    const base = (process.env.NEXT_PUBLIC_SITE_URL || "").replace(/\/$/, "");
    if (!base) throw new Error("NEXT_PUBLIC_SITE_URL is required");

    const tokenRows: Record<string, unknown>[] = [];
    const itemRows: Record<string, unknown>[] = [];
    const rendered: RenderedItem[] = [];
    let rank = 0;

    for (const item of ranked) {
      const paper = paperMap.get(item.paperId);
      if (!paper?.canonical_url) continue;
      const narrative = narratives.get(item.paperId);
      if (!narrative) throw new Error(`Summary missing for paper ${item.paperId}`);

      const section = sectionFor(item, rank);
      const metadata = { ranking: item, section };
      const actions: Array<[Action, string]> = [
        ["CLICK", "read"], ["SAVE", "save"], ["MORE_LIKE_THIS", "more"], ["LESS_LIKE_THIS", "less"],
      ];
      const links = {} as RenderedItem["links"];

      for (const [action, key] of actions) {
        const raw = token();
        links[key as keyof RenderedItem["links"]] = link(base, action, raw);
        tokenRows.push({
          token_hash: sha256(raw),
          user_id: userId,
          paper_id: item.paperId,
          digest_id: digestId,
          action_type: action,
          redirect_url: action === "CLICK" ? paper.canonical_url : null,
          expires_at: new Date(Date.now() + 45 * 86_400_000).toISOString(),
          single_use: action !== "CLICK",
          metadata,
        });
      }

      rank++;
      itemRows.push({
        digest_id: digestId,
        paper_id: item.paperId,
        rank,
        section,
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
      rendered.push({ paper, narrative, section, links });
    }

    if (!rendered.length) throw new Error("Digest contains no renderable papers");
    const { error: tokenError } = await db.from("interaction_tokens").insert(tokenRows);
    if (tokenError) throw tokenError;
    const { error: itemError } = await db.from("digest_items").insert(itemRows);
    if (itemError) throw itemError;

    const output = render(kind, profile.display_name, rendered);
    const subject = kind === "initial"
      ? `Your first Neurofeed — ${rendered.length} papers for you`
      : `Neurofeed Weekly — ${rendered.length} papers for you`;
    const { error: finishError } = await db.from("digests").update({
      subject,
      rendered_html: output.html,
      rendered_text: output.text,
      content_hash: sha256(`${output.html}\n${output.text}`),
      status: "GENERATED",
    }).eq("id", digestId);
    if (finishError) throw finishError;
    return digestId;
  } catch (error) {
    await db.from("digests").delete().eq("id", digestId);
    throw error;
  }
}

export function createInitialDigest(userId: string) {
  return createDigest(userId, "initial");
}

export function createWeeklyDigest(userId: string) {
  return createDigest(userId, "weekly");
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
  if (digest.status === "SENDING") return { sent: false, alreadySent: false, needsReview: true };
  if (digest.status !== "GENERATED") throw new Error(`Digest ${digestId} is not ready to send`);

  const { data: claimed, error: claimError } = await db
    .from("digests")
    .update({ status: "SENDING", delivery_error: null })
    .eq("id", digestId)
    .eq("status", "GENERATED")
    .select("id")
    .maybeSingle();
  if (claimError) throw claimError;
  if (!claimed) return { sent: false, alreadySent: false, needsReview: true };

  const { data: users, error: userError } = await db.rpc("get_newsletter_users");
  if (userError) throw userError;
  const recipient = (users || []).find((row: { user_id: string; email: string }) => row.user_id === digest.user_id)?.email;
  if (!recipient) {
    await db.from("digests").update({ status: "GENERATED", delivery_error: "Recipient unavailable" }).eq("id", digestId);
    throw new Error("Newsletter recipient email is unavailable");
  }

  const username = process.env.NEUROFEED_SMTP_USERNAME;
  const password = process.env.NEUROFEED_SMTP_PASSWORD;
  const from = process.env.NEUROFEED_EMAIL_FROM;
  if (!username || !password || !from) {
    await db.from("digests").update({ status: "GENERATED", delivery_error: "SMTP configuration incomplete" }).eq("id", digestId);
    throw new Error("SMTP configuration is incomplete");
  }

  let accepted = false;
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
    accepted = true;

    const { error: sentError } = await db.from("digests").update({
      status: "SENT",
      sent_at: new Date().toISOString(),
      delivery_provider: "gmail_smtp",
      delivery_id: result.messageId || messageId,
      delivery_error: null,
    }).eq("id", digestId).eq("status", "SENDING");
    if (sentError) throw sentError;

    const { data: items } = await db.from("digest_items").select("paper_id").eq("digest_id", digestId);
    if (items?.length) {
      const { error: impressionError } = await db.from("user_paper_events").insert(items.map((item) => ({
        user_id: digest.user_id,
        paper_id: item.paper_id,
        digest_id: digestId,
        event_type: "IMPRESSION",
        metadata: { source: "newsletter_delivery" },
      })));
      if (impressionError) console.error("Failed to record newsletter impressions", impressionError);
    }
    return { sent: true, alreadySent: false };
  } catch (error) {
    if (!accepted) {
      await db.from("digests").update({
        status: "GENERATED",
        delivery_error: String(error).slice(0, 1000),
      }).eq("id", digestId).eq("status", "SENDING");
    }
    throw error;
  }
}
