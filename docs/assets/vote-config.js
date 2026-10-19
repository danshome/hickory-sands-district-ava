// Where the growers' logo vote (logo-vote.html) reads and sends votes, and
// its switches. Public by design: nothing here is a secret.
//
// live: false until the switch-over (src/vote/SETUP.md). Until then the page
// only says "The vote moves here soon" and links to the current page; it
// calls nothing.
export const live = true;

// The Supabase Edge Function vote-api (src/vote/functions/vote-api/).
export const endpoint =
  "https://yayebhncbagmebwgmezd.supabase.co/functions/v1/vote-api";

// The person check, Cloudflare Turnstile: off while this is empty. To turn it
// on, set this to the widget's site key and VOTE_TURNSTILE_SECRET in Supabase
// to its secret, together ("If bots show up" in src/vote/SETUP.md).
export const turnstileSiteKey = "";

// Where a voter id may be carried over from (#voter=<id>): the Shopify vote
// page's origins (src/vote/shopify-handoff.liquid).
export const carryFrom = [
  "https://robertclayvineyards.com",
  "https://www.robertclayvineyards.com",
];

// When the vote closes, the petitioners set closed to true and chosen to the
// design's id ("c1", or "sub-<uuid>"). The page then shows that design as the
// growers' choice and stops taking votes and designs. It never picks the
// leader by itself.
export const closed = false;
export const chosen = "";
