# resources/vineyards: the vineyard outlines on the 3D aquifer page

Read by `src/site/make_aquifer_3d.py` (`src/site/aquifer/vineyards.py`) for `docs/aquifer.html` (#135). NAD83
(EPSG:4269), longitude first. Map context only: no boundary geometry comes from it.

`vineyards-EPSG4269.geojson`: one feature per vine block, with its vineyard's `name`, its `category`, its `block` (where a
vineyard has several: its number or a planned block's name, always as text, since the page's map takes a field's type
from its first value), the `acres` of its outline (not of planted vines) and `source`, a short note of where the name
and the outline come from. Vineyard names and outlines are published as they
are; no field holds a person's name, an e-mail, a telephone number or a street address, and the generator refuses one
that does.

| category | the page's layer | vineyards |
|---|---|---|
| `hsd` | Hickory Sands District vineyards | the confirmed blocks inside the proposed district: Blackmon, Certenburg, Parr, Peters Prairie, Pontotoc, Robert Clay, Tallent and Verasion Hills |
| `llano-uplift` | Llano Uplift vineyards | outside the district, inside TTB's proposed Llano Uplift AVA: 1900 Vineyard, Castell, Loyal Valley, Fall Creek, Perissos, Uplift, Torr Na Lochs, Purple Calf, and Heart of Art Vineyard |
| `under-development` | Under development | I Don't Know Vineyard (its 2022 outline) and Paisano Vineyards (two planned blocks, approximate, from its planting plan) |
| `historical` | Historical | Spiller Mine and Akashic (their 2022 outlines) |

Sources (each block's `source` says which):
- the petitioners' vineyard layer of October 2022, its vineyards checked one by one on NAIP 2022 (0.6 m, TxGIO
  `NAIP22_NCCIR_60cm`) and redrawn by eye as one polygon per vine block, on 2026-10-18; I Don't Know Vineyard and
  the historical vineyards keep their 2022 outlines;
- the Llano Uplift AVA petition's Table 1 (regulations.gov TTB-2026-0005-0006), each vineyard found at its Texas Wine
  Lover guide listing and outlined the same way; Purple Calf Vineyard, not in Table 1, was named and placed by the
  petitioner;
- Heart of Art Vineyard: the heart-shaped fenced plot outlined in the petitioners' response to Comment 8 (Comment 9,
  TTB-2026-0005-0018, Oct. 15, 2026) on USGS NAIP Plus imagery, about ±15 m;
- Paisano Vineyards: its two planned blocks, the Streeter Lane frontage and the east side along the pipeline easement,
  approximate: traced along the centre of their outlines on the owners' preliminary planting plan (October 2026),
  whose aerial image was fitted to NAIP 2022 by matching it at about 2,000 points (a projective fit, within about
  0.8 m RMS); the vineyard named by the petitioner. Site preparation is in progress for planting about 6 acres in
  2027 and 2028. Only the two blocks are kept, never the plan or the tract's boundary. The blocks' `source` says
  "the vineyard's preliminary planting plan", because the generator refuses the word "owner" in the vineyard data.

Left out: the 2022 outlines of the vineyards outlined again here (each is replaced by its blocks); the west Peters
Prairie block (left off, the petitioners' decision); Heart of Art's larger 2022 outline (Comment 9's block is used);
Comment 9's other two blocks (its main block is 1900 Vineyard's, and its east field shows rows faintly or not at all).
A vineyard whose place is not yet known is not drawn.

Not a survey: only the named vineyards were looked at, so other vineyards may exist; summer 2022 photographs may show
recent plantings, very young vines or dead blocks wrongly. Made from the vineyard check's outputs, Comment 9's block
file and the trace of the Paisano planting plan, kept outside the repository; to add or move a vineyard, edit this
file (a `category` from the table, a `source` note) and run `./build.sh site-data`.
