LIBFILES=$(wildcard library/*.lib)
DCMFILES=$(patsubst %.lib,%.dcm,${LIBFILES})
PVFILES=$(addprefix preview/,$(patsubst %.lib,%.md,$(notdir ${LIBFILES})))
IMAGECACHE:=$(shell mktemp)
DBFILES=$(shell find bomtool-db -type f)

TMPDIR := $(shell mktemp -d)

PCBLIB_PATH := "../pcblib"

.PHONY: all clean check

all: ${PVFILES}
	rm -f ${IMAGECACHE}
	@#./scripts/cleanup.py images

check: error-report.md
	@[ ! -f error-todo.md ] || diff -uwBd --color=always -I '^- \[x\]' -I '^#' error-todo.md $< && echo "No new errors" || true
	@[ ! -s $< ] || echo "Errors remain!, check $<" && false

error-report.md: ${LIBFILES}
	PYTHONUNBUFFERED=1 ./scripts/tests.py \
		-k --pcblib-path ${PCBLIB_PATH} library \
	| tee -i $@

clean:
	rm -rf preview/
	rm -f error-report.md

preview/%.md: library/%.lib
	mkdir -p preview/images
	if [ -f $(patsubst %.lib,%.dcm,$<) ]; then \
		./scripts/schlib-render.py preview/images /images ${IMAGECACHE} $< $(patsubst %.lib,%.dcm,$<) > $@; \
	else \
		./scripts/schlib-render.py preview/images /images ${IMAGECACHE} $< > $@; \
	fi
