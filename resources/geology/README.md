# resources/geology: the geology shown with the boundary

Context only: no boundary geometry comes from these layers. NAD83 (EPSG:4269), longitude first.

| file | what it is | read by |
|---|---|---|
| `usgs-sgmc-geology-shifted-to-naip-EPSG4269.gpkg` | three USGS units, shifted to sit on the outcrops: `Town_Mountain_Granite` (68 polygons), `Younger_granitic_intrusions` (62), `Hickory_Sandstone_Member_formation` (95) | `src/publish/agol_layer.py` (layer 4m and the web map 4a); `src/site/make_aquifer_3d.py` (the Hickory Sandstone Member of the Riley Formation on the 3D aquifer page, and the same shift applied to TWDB's 2017 Hickory outline) |

Source: USGS State Geologic Map Compilation (Horton and others, 2017, USGS Data Series 1052), Texas units TXpCAt;0,
TXpCAy;0 and TXCAh;0; public domain. SGMC as published sits about 400 m south-east of the outcrops on USDA NAIP
imagery, so every polygon is shifted -0.002356 deg longitude and +0.002993 deg latitude (about 225 m west, 331 m north,
fitted to the granite outcrop trace). Each feature carries its source, unit link and the shift in its `alignment` field.

Made on Oct. 13, 2026 by the old comment pipeline's `build_geology.py` (since retired); this is the copy uploaded with the
Oct. 15 Grit-options map. Use these shifted layers, not SGMC as published, for any granite or Hickory Sandstone Member
figure or map.
