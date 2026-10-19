// Where "Add your vineyard" (vineyards.html) sends a vineyard, and the
// Cloudflare Turnstile widget it shows. Both are public by design: the
// function's address, and Turnstile's Site Key (its Secret Key lives only in
// Supabase). Dan sets them once the function is deployed
// (src/vineyards/SETUP.md, step 9). While either is empty, the form still
// works through its five steps and then offers to send the details by email.
//
// endpoint: https://yayebhncbagmebwgmezd.supabase.co/functions/v1/vineyard-submit
export const endpoint = "";
export const turnstileSiteKey = "";
