LIBFILES=$(wildcard library/*.lib)
DCMFILES=$(patsubst %.lib,%.dcm,${LIBFILES})
PVFILES=$(addprefix preview/,$(patsubst %.lib,%.md,$(notdir ${LIBFILES})))
TESTFILES=$(addprefix test-results/,$(notdir ${PVFILES}))
IMAGECACHE:=$(shell mktemp)
DBFILES=$(shell find bomtool-db -type f)

TMPDIR := $(shell mktemp -d)

PCBLIB_PATH := "../pcblib"

.PHONY: all clean check

all: ${PVFILES}
	rm -f ${IMAGECACHE}
	@#./scripts/cleanup.py images

check: error-report.md
	@if [ -d test-todo ]; then \
		diff -uwBdN -x '*~' --color=always -I '^- \[x\]' -I '^#' \
		test-todo test-results && echo "No new errors" || true ; \
	fi
	@[ ! -s  $< ] || echo "Errors remain!, check $<" && false

test-todo: ${TESTFILES}
	mkdir -p $@
	@echo 'cp $$TESTFILES $@/'
	@cp $^ $@/
	find $@ -empty -type f -delete

error-report.md: ${TESTFILES}
	@echo 'cat $$TESTFILES > $@'
	@cat $^ > $@

test-results:
	mkdir -p $@

test-results/%.md: library/%.lib | test-results
	./scripts/tests.py -k --pcblib-path ${PCBLIB_PATH} $< > $@

clean:
	rm -rf preview/
	rm -rf test-results/
	rm -f error-report.md

distclean: clean
	rm -rf test-todo/

preview/%.md: library/%.lib
	mkdir -p preview/images
	if [ -f $(patsubst %.lib,%.dcm,$<) ]; then \
		./scripts/schlib-render.py preview/images /images ${IMAGECACHE} $< $(patsubst %.lib,%.dcm,$<) > $@; \
	else \
		./scripts/schlib-render.py preview/images /images ${IMAGECACHE} $< > $@; \
	fi
