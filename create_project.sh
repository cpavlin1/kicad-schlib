#!/bin/bash

SCHLIB_URL="${SCHLIB_URL:-git@github.com:cpavlina/kicad-schlib}"
PCBLIB_URL="${PCBLIB_URL:-git@github.com:cpavlina/kicad-pcblib}"

BN="$(basename "$0")"

set -e

function tagline() {
    echo
    echo "$BN: create a new KiCad project using these libraries"
}

function usage() {
    echo
    echo "Usage:"
    echo " $BN -h|--help"
    echo " $BN [--] projectname"
}

function main() {
    case "$1" in
        "")
            tagline
            exit 0
            ;;
        -h|--help|"")
            tagline
            usage
            exit 0
            ;;
        --)
            shift 1
            ;;
        -*)
            echo "$BN: unknown argument $1"
            exit 1
            ;;
    esac

    if ! command -v git >/dev/null 2>&1; then
        echo "error: $BN requires git" >&2
        exit 1
    fi

    PROJECT_NAME="$1"

    if [[ -e "$PROJECT_NAME" ]]; then
        echo "error: \"$PROJECT_NAME\" already exists" >&2
        exit 1
    fi

    mkdir -p "$PROJECT_NAME"
    cd "$PROJECT_NAME"

    # Initialize git repository only if we're not in one already
    if ! in_git_repo; then
        git init
    fi

    install_submodules
    make_gitignore

    make_fp_lib_table "fp-lib-table"
    make_sym_lib_table "sym-lib-table"
    make_project "$PROJECT_NAME" "${PROJECT_NAME}.pro"
}

function install_submodules() {
    git submodule add --depth 1 "$SCHLIB_URL" schlib
    git submodule add --depth 1 "$PCBLIB_URL" pcblib
}

function make_fp_lib_table() {
    echo "(fp_lib_table" > "$1"
    for i in pcblib/*.pretty; do
        # Only add IPC7351-Nominal, not Least or Most
        if [[ "$i" == *'/IPC7351-Most.pretty' ]] || [[ "$i" == *'/IPC7351-Least.pretty' ]]; then
            continue
        fi

        filename="$(basename "$i")"
        libname="${filename/%.pretty/}"

        echo "  (lib (name \"$libname\")(type KiCad)(uri \"\$(KIPRJMOD)/$i\")(options \"\")(descr \"\"))" >>"$1"
    done
    echo ")" >>"$1"
}

function make_sym_lib_table() {
    echo "(sym_lib_table" > "$1"
    find schlib/library -maxdepth 1 -name '*.lib' -type f -print0 | sort -zfV |
    while read -r -d $'\0' i; do
        filename="$(basename "$i")"
        libname="${filename/%.lib/}"

        echo "  (lib (name \"$libname\")(type Legacy)(uri \"\$(KIPRJMOD)/$i\")(options \"\")(descr \"\"))" >>"$1"
    done
    echo ")" >>"$1"
}

function make_project() {
    name="$1"
    filename="$2"

    echo -n "update=" >"$filename"
    date '+%a %d %b %Y %I:%M:%S %p %Z' >>"$filename"
    cat >>"$filename" <<EOF
version=1
last_client=kicad
[cvpcb]
version=1
NetIExt=net
[general]
version=1
[eeschema]
version=1
LibDir=kicad-schlib/library
[eeschema/libraries]
EOF
    count=1 # kicad, this is fucking stupid
    for i in schlib/library/*.lib; do
        libname="${i/%.lib/}"
        echo "LibName${count}=${libname}" >>"$filename"
        count=$((count + 1))
    done
    cat >>"$filename" <<EOF
[schematic_editor]
version=1
PageLayoutDescrFile=schlib/page_layouts/basic.kicad_wks
PlotDirectoryName=
SubpartIdSeparator=0
SubpartFirstId=65
NetFmtName=
SpiceForceRefPrefix=0
SpiceUseNetNumbers=0
LabSize=60
ERC_TestSimilarLabels=1
[pcbnew]
version=1
PageLayoutDescrFile=pcblib/page_layouts/empty.kicad_wks
LastNetListRead=
PadDrill=0.762
PadDrillOvalY=0.762
PadSizeH=1.524
PadSizeV=1.524
PcbTextSizeV=1.5
PcbTextSizeH=1.5
PcbTextThickness=0.3
ModuleTextSizeV=1
ModuleTextSizeH=1
ModuleTextSizeThickness=0.15
SolderMaskClearance=0.2
SolderMaskMinWidth=0
DrawSegmentWidth=0.2
BoardOutlineThickness=0.15
ModuleOutlineThickness=0.15
EOF
}

function make_gitignore () {
    cat >> ".gitignore" <<EOF
# KiCAD temporary files
*.cmp
*.net
# KiCAD backups and autosaves
*.bak
*.bck
*.kicad_pcb-bak
*.v4
_saved_*
_autosave-*
# Editor backups and autosaves
*~
\#*\#
.\#*
EOF
}

function in_git_repo() {
    if [ -d .git ] || git rev-parse --git-dir >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

main "$@"
