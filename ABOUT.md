# About

**Hickory Sands District** is a proposed American Viticultural Area (AVA) in the Llano Uplift region of the Texas Hill
Country, in parts of Llano, Mason, McCulloch and San Saba Counties. It becomes an AVA only if the Alcohol and Tobacco Tax
and Trade Bureau (TTB) establishes it in a final rule.

This repository and the website [hickorysandsdistrictava.org](https://hickorysandsdistrictava.org) are the
petitioners' work. They are independent of TTB and do not speak for it.

## The people

Three growers petitioned TTB to establish Hickory Sands District:

- Dan McLaughlin, of Robert Clay Vineyards
- William R. Parr, Jr., of Parr Vineyards and Parr Cellars
- Drew Tallent, of Tallent Vineyards

**Tesha Parr Solomon**, of Parr Cellars and Parr Vineyards, coordinated the petition and wrote it. **Dan McLaughlin**
wrote the boundary narrative, drew the boundary, and did all the spatial work for the GIS layers.

## The official record

TTB's record of the proposal is the one that counts:

| | |
|---|---|
| **Notice No. 243** (TTB's proposed rule, 91 FR 52576) | https://www.federalregister.gov/d/2026-16670 |
| **The public docket** (the notice, the petition and the public comments) | https://www.regulations.gov/docket/TTB-2026-0005 |
| **TTB's AVA Map Explorer** | https://www.ttb.gov/ava |

## Where to look

| | |
|---|---|
| **The website** | [hickorysandsdistrictava.org](https://hickorysandsdistrictava.org): the place, the boundary, the map, the vineyards, and [where the proposal stands](https://hickorysandsdistrictava.org/status.html) |
| **The boundary, step by step** | [Walk the line](https://hickorysandsdistrictava.org/walk.html) |
| **The ArcGIS Online dashboard** | https://robertclayvines.maps.arcgis.com/apps/dashboards/c5de8bb3fc1348d99f8afd99c11220b2 |
| **This repository** | [README.md](README.md) (what is proposed, and the build's figures), [BUILD.md](BUILD.md) (how it is built), [CONTRIBUTING.md](CONTRIBUTING.md) (how to help) |

## How this repository works

Everything that goes to TTB is built from source with one command, `./build.sh`:

- the boundary description;
- TTB's notice with the proposed changes highlighted;
- a side-by-side comparison;
- the GIS layers;
- the 13 USGS 1:24,000 quadrangles with the boundary drawn on them.

Every line of the boundary is drawn on the printed linework of those USGS maps, and none is copied from an existing
boundary layer. The website's maps and figures come from the same build.

## Contact

- **The district:** [district@hickorysandsdistrictava.org](mailto:district@hickorysandsdistrictava.org)
- **A security problem:** report it privately, as [SECURITY.md](SECURITY.md) explains, not in a public issue.

## License

The petitioners' work here is dedicated to the public domain under CC0 1.0 ([LICENSE.txt](LICENSE.txt)). Everyone taking
part follows the [Code of Conduct](CODE_OF_CONDUCT.md).
