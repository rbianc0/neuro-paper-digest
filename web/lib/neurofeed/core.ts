import { createHash, randomBytes } from "node:crypto";

export const NEUROFEED = {
  embeddingModel: "text-embedding-3-small",
  embeddingDimensions: 1536,
  lookbackDays: 21,
  targetPapers: 16,
  semanticCandidates: 400,
  broadCandidates: 200,
  priorityVenues: new Set([
    "nature",
    "science",
    "cell",
    "nature neuroscience",
    "neuron",
    "nature human behaviour",
    "current biology",
    "proceedings of the national academy of sciences",
    "science advances",
    "nature communications",
  ]),
  weights: {
    semantic: 0.35,
    bluesky: 0.30,
    fit: 0.10,
    quality: 0.10,
    broad: 0.05,
    novelty: 0.05,
    recency: 0.05,
  },
} as const;

export type RankedPaper = {
  paperId: string;
  finalScore: number;
  semanticScore: number;
  blueskyScore: number;
  fitScore: number;
  qualityScore: number;
  broadScore: number;
  noveltyScore: number;
  recencyScore: number;
  lane: "focused" | "broad";
  provenance: Record<string, unknown>;
};

export function clamp(value: number) {
  return Math.max(0, Math.min(1, value));
}

export function normalizeText(...parts: Array<string | null | undefined>) {
  return parts
    .filter((part): part is string => Boolean(part?.trim()))
    .map((part) => part.trim().replace(/\s+/g, " "))
    .join("\n\n");
}

export function sha256(value: string) {
  return createHash("sha256").update(value).digest("hex");
}

export function token() {
  return randomBytes(32).toString("base64url");
}

export function vectorLiteral(values: number[]) {
  return `[${values.map((value) => Number(value).toPrecision(10)).join(",")}]`;
}

export function canonicalDoi(raw: string | null | undefined) {
  if (!raw) return null;
  const value = raw
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\/(dx\.)?doi\.org\//, "")
    .replace(/^doi:\s*/, "");
  return value.startsWith("10.") ? value : null;
}

export function normalizedTitle(raw: string | null | undefined) {
  return (raw || "")
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

export function isoDateDaysAgo(days: number) {
  const value = new Date();
  value.setUTCDate(value.getUTCDate() - days);
  return value.toISOString().slice(0, 10);
}

export function ageDays(raw: string | null | undefined) {
  if (!raw) return 999;
  const time = Date.parse(raw);
  if (!Number.isFinite(time)) return 999;
  return Math.max(0, (Date.now() - time) / 86_400_000);
}

export function saturatingCount(value: unknown, scale: number) {
  return 1 - Math.exp(-Math.max(0, Number(value) || 0) / scale);
}
