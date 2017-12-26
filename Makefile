LIBFILES=$(wildcard library/*.lib)
DCMFILES=$(patsubst %.lib,%.dcm,${LIBFILES})
PVFILES=$(addprefix preview/,$(patsubst %.lib,%.md,$(notdir ${LIBFILES})))
IMAGECACHE:=$(shell mktemp)
DBFILES=$(shell find bomtool-db -type f)

TMPDIR := $(shell mktemp -d)

PCBLIB_PATH := "../pcblib"

.PHONY: all clean

all: ${PVFILES}
	rm -f ${IMAGECACHE}
	@#./scripts/cleanup.py images

test:
	./scripts/tests.py --pcblib-path ${PCBLIB_PATH} library

clean:
	rm -rf preview/

preview/%.md: library/%.lib
	mkdir -p preview/images
	if [ -f $(patsubst %.lib,%.dcm,$<) ]; then \
		./scripts/schlib-render.py preview/images /images ${IMAGECACHE} $< $(patsubst %.lib,%.dcm,$<) > $@; \
	else \
		./scripts/schlib-render.py preview/images /images ${IMAGECACHE} $< > $@; \
	fi
