// The site's vineyard data (assets/vineyards/, made by
// src/site/make_vineyards.py), always as it is now. GitHub Pages serves every
// file with cache-control: max-age=600, so a browser that loaded the data
// shortly before a vineyard change was merged would keep the old names and
// outlines for ten minutes. The scripts' own URLs carry a version
// (src/site/stamp_assets.py, #138); the data's carry the data's stamp,
// read from its record, which is small and fetched revalidated (a 304 when
// unchanged): each vineyard file is then loaded as name?v=stamp, a new URL
// whenever any vineyard file changes. Every page that reads vineyard data
// does so through vineyardUrl() or vineyardJson() (tests/test_vineyard_data_urls.py).
//
// When the record cannot be read, the files are named without a stamp and
// fetched revalidated where the page fetches them itself; the page works.

const FOLDER = "assets/vineyards/";
const STAMP = /^[0-9a-f]{7,64}$/;

let stamping = null;
// The data's stamp, read once; null when the record could not be read.
function stamp() {
  stamping ||= fetch(`${FOLDER}record.json`, { cache: "no-cache" })
    .then((r) => (r.ok ? r.json() : null))
    .then((record) => {
      const value = record && typeof record === "object" ? record.stamp : null;
      return typeof value === "string" && STAMP.test(value) ? value : null;
    })
    .catch((error) => {
      console.warn("the vineyard data's record could not be read", error);
      return null;
    });
  return stamping;
}

// The URL of one vineyard file (as "vineyards.geojson"), with the stamp.
export async function vineyardUrl(name) {
  const v = await stamp();
  return v ? `${FOLDER}${name}?v=${v}` : `${FOLDER}${name}`;
}

// One vineyard JSON file, fetched by its stamped URL, or revalidated when
// there is no stamp. Throws when it cannot be loaded.
export async function vineyardJson(name) {
  const v = await stamp();
  const url = v ? `${FOLDER}${name}?v=${v}` : `${FOLDER}${name}`;
  const r = await fetch(url, v ? {} : { cache: "no-cache" });
  if (!r.ok) throw new Error(`${FOLDER}${name}: HTTP ${r.status}`);
  return r.json();
}
