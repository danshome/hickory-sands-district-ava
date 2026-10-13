# Entry points. See README, "Rebuilding large files".
PYTHON ?= python3
export PYTHON

.PHONY: all fetch build quads geology check stage package clean

all: build check

fetch:            ## download the 13 USGS quads and the docket source PDFs
	$(PYTHON) scripts/fetch_quads.py
	$(PYTHON) scripts/fetch_sources.py

quads:            ## neatline-cropped quad GeoTIFFs (needs GDAL and make fetch)
	scripts/build_cropped_quads.sh

geology:          ## USGS SGMC geology and the 1,500 ft Hickory Sands layer into build/geology/ (needs GDAL)
	$(PYTHON) scripts/build_geology.py

build:            ## exhibits, thumbnails, comment PDFs and shapefiles into build/
	scripts/build_all.sh

check:            ## read-only consistency checks
	scripts/check.sh

stage: build      ## copy built PDFs and layers into the private filing kit (keeps signed PDFs unless FORCE=1)
	scripts/stage_filing.sh
	scripts/check.sh

package:          ## after signing: zip the 12 upload files and write COMMENT-BOX.txt into .local/filing/
	scripts/package_filing.sh

clean:
	rm -rf build
