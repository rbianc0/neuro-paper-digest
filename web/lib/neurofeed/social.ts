import "server-only";

import { createSupabaseServiceClient } from "@/lib/supabase/service";
import { bsky } from "./bluesky";
import { canonicalDoi } from "./core";

const DOI_RE = /10\.\d{4,9}\/[-._;()/:a-z0-9]+/gi;
const URL_RE = /https?:\/\/[^\s<>\]\[)("']+/gi;
const SCHOLARLY_HOSTS = [
  "doi.org", "biorxiv.org", "medrxiv.org", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
  "nature.com", "science.org", "cell.com", "sciencedirect.com", "springer.com", "wiley.com",
  "academic.oup.com", "jneurosci.org", "elifesciences.org", "plos.org", "frontiersin.org",
  "tandfonline.com", "cambridge.org", "arxiv.org", "openalex.org",
];

type FeedItem = {
  reason?: { $type?: string; indexedAt?: string; uri?: string };
  post?: {
    uri?: string;
    cid?: string;
    indexedAt?: string;
    author?: { did?: string; handle?: string; displayName?: string; description?: string; avatar?: string };
    record?: { text?: string; createdAt?: string; embed?: unknown; facets?: unknown };
    embed?: unknown;
  };
};

type ScholarlyLink = { linkKey: string; url: string; doi: string | null; pmid: string | null };

function* strings(value: unknown): Generator<string> {
  if (typeof value === "string") yield value;
  else if (Array.isArray(value)) for (const item of value) yield* strings(item);
  else if (value && typeof value === "object") for (const item of Object.values(value)) yield* strings(item);
}

function scholarlyUrl(raw: string) {
  try {
    const host = new URL(raw).hostname.toLowerCase().replace(/^www\./, "");
    return SCHOLARLY_HOSTS.some((allowed) => host === allowed || host.endsWith(`.${allowed}`));
  } catch {
    return false;
  }
}

function pmid(raw: string) {
  return raw.match(/(?:pubmed\.ncbi\.nlm\.nih\.gov\/|\/pubmed\/)(\d+)/i)?.[1] || null;
}

function links(item: FeedItem) {
  const record = item.post?.record || {};
  const foundUrls = new Set<string>();
  const foundDois = new Set<string>();
  const foundPmids = new Set<string>();
  const values = [record.text || "", ...strings({ facets: record.facets, embed: record.embed, viewEmbed: item.post?.embed })];

  for (const value of values) {
    for (const raw of value.match(URL_RE) || []) {
      const url = raw.replace(/[.,;:)]+$/, "");
      if (scholarlyUrl(url)) foundUrls.add(url);
      const id = pmid(url);
      if (id) foundPmids.add(id);
      const doi = canonicalDoi(url);
      if (doi) foundDois.add(doi);
    }
    for (const raw of value.match(DOI_RE) || []) {
      const doi = canonicalDoi(raw);
      if (doi) foundDois.add(doi);
    }
  }

  const output = new Map<string, ScholarlyLink>();
  for (const doi of foundDois) output.set(`doi:${doi}`, { linkKey: `doi:${doi}`, doi, pmid: null, url: `https://doi.org/${doi}` });
  for (const id of foundPmids) output.set(`pmid:${id}`, { linkKey: `pmid:${id}`, doi: null, pmid: id, url: `https://pubmed.ncbi.nlm.nih.gov/${id}/` });
  for (const url of foundUrls) output.set(`url:${url}`, { linkKey: `url:${url}`, doi: canonicalDoi(url), pmid: pmid(url), url });
  return [...output.values()];
}

function signalType(item: FeedItem): "POST" | "REPOST" | "QUOTE" {
  if (item.reason?.$type?.endsWith("#reasonRepost")) return "REPOST";
  const embed = item.post?.record?.embed as { $type?: string } | undefined;
  return embed?.$type?.includes("embed.record") || embed?.$type?.includes("recordWithMedia") ? "QUOTE" : "POST";
}

function eventTime(item: FeedItem) {
  return item.reason?.indexedAt || item.post?.record?.createdAt || item.post?.indexedAt || null;
}

async function authorFeed(actor: string, lookbackDays: number) {
  const since = Date.now() - lookbackDays * 86_400_000;
  const events: FeedItem[] = [];
  let cursor: string | undefined;

  for (let page = 0; page < 5; page++) {
    const data = await bsky<{ feed?: FeedItem[]; cursor?: string }>("app.bsky.feed.getAuthorFeed", {
      actor,
      limit: 100,
      filter: "posts_with_replies",
      ...(cursor ? { cursor } : {}),
    });
    const feed = data.feed || [];
    if (!feed.length) break;
    let reachedOld = false;
    for (const item of feed) {
      const time = eventTime(item);
      if (time && Date.parse(time) < since) {
        reachedOld = true;
        continue;
      }
      if (links(item).length) events.push(item);
    }
    if (reachedOld || !data.cursor) break;
    cursor = data.cursor;
  }
  return events;
}

async function persistAccountFeed(actorDid: string, lookbackDays: number) {
  const db = createSupabaseServiceClient();
  const feed = await authorFeed(actorDid, lookbackDays);
  const posts = [];
  const events = [];
  const scholarlyLinks = [];

  for (const item of feed) {
    const post = item.post;
    const author = post?.author;
    const uri = post?.uri;
    const timestamp = eventTime(item);
    if (!post || !author?.did || !uri || !timestamp) continue;
    const itemLinks = links(item);
    if (!itemLinks.length) continue;
    const type = signalType(item);
    const record = post.record || {};
    const eventKey = item.reason?.uri || `${actorDid}|${type}|${uri}|${timestamp}`;

    posts.push({
      uri,
      cid: post.cid || null,
      author_did: author.did,
      text: record.text || "",
      created_at: record.createdAt || null,
      indexed_at: post.indexedAt || null,
      post_type: type === "QUOTE" ? "QUOTE" : "POST",
      referenced_uri: null,
      extracted_urls: itemLinks.map((link) => link.url),
      raw_record: record,
    });
    events.push({
      event_key: eventKey,
      post_uri: uri,
      actor_did: actorDid,
      signal_type: type,
      signal_timestamp: timestamp,
      event_uri: item.reason?.uri || null,
      raw_event: { reason: item.reason || null },
    });
    for (const link of itemLinks) {
      scholarlyLinks.push({
        post_uri: uri,
        link_key: link.linkKey,
        url: link.url,
        doi: link.doi,
        pmid: link.pmid,
      });
    }
  }

  if (posts.length) {
    const authorProfiles = [...new Map(feed.flatMap((item) => {
      const author = item.post?.author;
      return author?.did ? [[author.did, {
        did: author.did,
        handle: author.handle || null,
        display_name: author.displayName || null,
        description: author.description || null,
        profile_metadata: { avatar: author.avatar || null },
        last_profile_fetched_at: new Date().toISOString(),
      }]] : [];
    })).values()];
    if (authorProfiles.length) {
      const { error } = await db.from("bluesky_accounts").upsert(authorProfiles, { onConflict: "did" });
      if (error) throw error;
    }
    const { error: postError } = await db.from("bluesky_posts").upsert(posts, { onConflict: "uri" });
    if (postError) throw postError;
    const { error: eventError } = await db.from("bluesky_post_events").upsert(events, { onConflict: "event_key" });
    if (eventError) throw eventError;
    const { error: linkError } = await db.from("bluesky_scholarly_links").upsert(scholarlyLinks, { onConflict: "post_uri,link_key" });
    if (linkError) throw linkError;
  }

  const { error: accountError } = await db.from("bluesky_accounts").update({
    last_feed_fetched_at: new Date().toISOString(),
    fetch_state: "OK",
    error_count: 0,
    next_fetch_after: null,
    last_error: null,
  }).eq("did", actorDid);
  if (accountError) throw accountError;
  return events.length;
}

export async function userFollowedDids(userId: string) {
  const db = createSupabaseServiceClient();
  const { data, error } = await db
    .from("user_bluesky_follows")
    .select("followed_did")
    .eq("user_id", userId)
    .eq("active", true);
  if (error) throw error;
  return (data || []).map((row) => row.followed_did as string);
}

export async function syncScholarlyFeeds(dids: string[], lookbackDays = 8) {
  let events = 0;
  let failed = 0;
  for (let offset = 0; offset < dids.length; offset += 8) {
    const results = await Promise.allSettled(dids.slice(offset, offset + 8).map((did) => persistAccountFeed(did, lookbackDays)));
    for (const result of results) {
      if (result.status === "fulfilled") events += result.value;
      else failed++;
    }
  }
  return { accounts: dids.length, events, failed };
}

export async function resolveScholarlyLinks(limit = 2000) {
  const db = createSupabaseServiceClient();
  const { data: pending, error } = await db
    .from("bluesky_scholarly_links")
    .select("id,post_uri,doi,pmid")
    .in("resolution_status", ["PENDING", "UNRESOLVED"])
    .not("doi", "is", null)
    .limit(limit);
  if (error) throw error;
  if (!pending?.length) return 0;

  const dois = [...new Set(pending.map((link) => link.doi).filter(Boolean))] as string[];
  const paperByDoi = new Map<string, string>();
  for (let offset = 0; offset < dois.length; offset += 100) {
    const { data, error: identifierError } = await db
      .from("paper_identifiers")
      .select("identifier_value,paper_id")
      .eq("identifier_type", "DOI")
      .in("identifier_value", dois.slice(offset, offset + 100));
    if (identifierError) throw identifierError;
    for (const row of data || []) paperByDoi.set(row.identifier_value, row.paper_id);
  }

  const resolved = pending.flatMap((link) => {
    const paperId = link.doi ? paperByDoi.get(link.doi) : undefined;
    return paperId ? [{ ...link, paperId }] : [];
  });
  if (!resolved.length) return 0;

  const postUris = [...new Set(resolved.map((link) => link.post_uri))];
  const allEvents = [];
  for (let offset = 0; offset < postUris.length; offset += 100) {
    const { data, error: eventError } = await db
      .from("bluesky_post_events")
      .select("post_uri,actor_did,signal_type,signal_timestamp")
      .in("post_uri", postUris.slice(offset, offset + 100));
    if (eventError) throw eventError;
    allEvents.push(...(data || []));
  }

  const eventsByPost = new Map<string, typeof allEvents>();
  for (const event of allEvents) {
    const list = eventsByPost.get(event.post_uri) || [];
    list.push(event);
    eventsByPost.set(event.post_uri, list);
  }
  const signals = resolved.flatMap((link) => (eventsByPost.get(link.post_uri) || []).map((event) => ({
    paper_id: link.paperId,
    post_uri: link.post_uri,
    actor_did: event.actor_did,
    signal_type: event.signal_type,
    signal_timestamp: event.signal_timestamp,
  })));
  if (signals.length) {
    const { error: signalError } = await db
      .from("paper_social_signals")
      .upsert(signals, { onConflict: "paper_id,post_uri,actor_did,signal_type" });
    if (signalError) throw signalError;
  }

  for (const link of resolved) {
    const { error: linkError } = await db.from("bluesky_scholarly_links").update({
      resolved_paper_id: link.paperId,
      resolution_status: "RESOLVED",
      last_attempted_at: new Date().toISOString(),
      last_error: null,
    }).eq("id", link.id);
    if (linkError) throw linkError;
  }
  return resolved.length;
}
