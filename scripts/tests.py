#!/usr/bin/env python3

import os
import sys
import argparse
import kicad_schlib

from urllib.request import urlopen, Request
from urllib.error import URLError
datasheet_links = {}

def check_ds_link(url):
    if not url in datasheet_links:
        request = Request(url)
        request.get_method = lambda : 'HEAD'
        request.add_header("User-Agent", "Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:47.0) Gecko/20100101 Firefox/47.0")
        try:
            response = urlopen(request, timeout=5)
            datasheet_links[url] = response.getcode()
        except URLError as e:
            datasheet_links[url] = getattr(e, 'code', str(e))
        except Exception as e:
            datasheet_links[url] = str(e)
        # Some 'special' hosts dont implement the HEAD method
        if datasheet_links[url] == 405:
            try:
                request.get_method = lambda : 'GET'
                response = urlopen(request, timeout=3)
                datasheet_links[url] = response.getcode()
            except URLError as e:
                datasheet_links[url] = getattr(e, 'code', str(e))
            except Exception as e:
                datasheet_links[url] = str(e)
    return datasheet_links[url]

PCBLIB_PATH = "../../pcblib" # Path relative to the library directory in a mock project

test_functions = []
test_notpl_functions = []

def register(f):
    test_functions.append(f)
    return f

def register_notpl(f):
    test_notpl_functions.append(f)
    return f

@register
def fields_50mil(part):
    """Field text size must be 50mil"""
    for i in part.fields:
        if i.visible and i.value != "" and not part.is_power:
            assert i.size == 50, "field name: %r, value: %r" % (i.name, i.value)


@register
def name_check(part):
    """Name check"""
    for c in ":/\\":
        assert c not in part.def_name, "Forbidden character '{}' in symbol name".format(c)


@register_notpl
def footprint_check(part):
    """Footprint check"""
    fp = part.footprint.split(":")
    assert not part.footprint or len(fp) == 2, "Invalid footprint '%s'" % part.footprint
    if part.footprint:
        libname = fp[0] + ".pretty"
        fpname = fp[1] + ".kicad_mod"
        fppath = os.path.join(PCBLIB_PATH, libname, fpname)
        assert os.path.isfile(fppath), "Footprint file '%s' does not exist" % fppath


@register_notpl
def datasheet_check(part):
    """Datasheet check"""
    if part.datasheet == "":
        return # Blank datasheet ok
    assert part.datasheet.startswith("http"), "'{}' is an invalid URL".format(part.datasheet)
    code = check_ds_link(part.datasheet)
    assert code in (200,301,302), "link '{}' BROKEN, error code '{}'".format(part.datasheet, code)


def main(args):
    full_fn = args.path
    fn = os.path.basename(full_fn)
    with open(full_fn) as f:
        reader = kicad_schlib.FileReader(f)

        try:
            lib = kicad_schlib.Library.parse(reader)
        except kicad_schlib.KiSyntaxError as e:
            print("# %s - cannot parse" % full_fn)
            print(str(e))
            return 2

        lib_success = True
        tests = test_functions + test_notpl_functions if not fn.startswith("_") else []
        for each_part in lib.parts:
            part_success = True
            for each_fxn in tests:
                try:
                    each_fxn(each_part)
                except Exception as e:
                    if lib_success:
                        print("# Library '{}'".format(full_fn))
                        lib_success = False
                    if part_success:
                        print("\n## Part '{}'".format(each_part.name))
                        part_success = False
                    print("- [ ] {}: {}".format(each_fxn.__doc__, str(e)))
                    if not args.keep_going:
                        break

        if not lib_success:
            print()
            if not args.keep_going:
                return 1
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-k","--keep-going", action="store_true", help="Keep testing even if failed")
    parser.add_argument("--pcblib-path", type=str, help="Path to the PCB library")
    parser.add_argument("path", help="Path of the schematic library to test")
    args = parser.parse_args()

    if args.pcblib_path:
        PCBLIB_PATH = args.pcblib_path
    else:
        PCBLIB_PATH = os.path.join(os.path.dirname(args.path), PCBLIB_PATH)

    sys.exit(main(args))
