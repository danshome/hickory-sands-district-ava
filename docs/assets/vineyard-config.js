// Where "Add your vineyard" (vineyards.html) sends a vineyard, and, only if
// it is ever needed, the Cloudflare Turnstile widget it shows. Both are
// public by design: the function's address, and Turnstile's Site Key (its
// Secret Key lives only in Supabase). Dan sets endpoint once the function is
// deployed (src/vineyards/SETUP.md, step 7). While endpoint
// is empty, the form still works through its five steps and then offers to
// send the details by email. turnstileSiteKey stays empty unless bots show
// up (SETUP.md, B, "If bots show up"): empty, there is no person check, and the
// form sends without one.
//
// endpoint: https://yayebhncbagmebwgmezd.supabase.co/functions/v1/vineyard-submit
export const endpoint = "https://yayebhncbagmebwgmezd.supabase.co/functions/v1/vineyard-submit";
export const turnstileSiteKey = "";
