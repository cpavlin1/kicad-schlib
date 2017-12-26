#!/usr/bin/python3

import cairo
import math
import shlex
import subprocess
from decimal import Decimal
import sys
import os
import copy
import subprocess
import pickle

COLOR_FG = (0.51765, 0.0, 0.0)
COLOR_BG = (1.0, 1.0, 0.76078)
COLOR_PN = (0.0, 0.51765, 0.51765)
MIN_WIDTH = 5
TEXT_OFFS = 10
MILS_PER_PIXEL = 5

class BoundingBox(object):
    def __init__(self, minx, maxx, miny, maxy):
        self.minx = minx
        self.maxx = maxx
        self.miny = miny
        self.maxy = maxy

    def __add__(self, other):
        if other == 0:
            return BoundingBox(self.minx, self.maxx, self.miny, self.maxy)
        return BoundingBox(
                min(self.minx, other.minx),
                max(self.maxx, other.maxx),
                min(self.miny, other.miny),
                max(self.maxy, other.maxy))
    __radd__ = __add__

    def __repr__(self):
        return "BoundingBox(%r, %r, %r, %r)" % (
                self.minx, self.maxx, self.miny, self.maxy)

    __str__ = __repr__

    @property
    def width(self):
        return self.maxx - self.minx
    @property
    def height(self):
        return self.maxy - self.miny
    @property
    def centerx(self):
        return (self.maxx + self.minx) / 2
    @property
    def centery(self):
        return (self.maxy + self.miny) / 2

class LineParser(object):
    def __init__(self, f):
        """Initialize a LineParser from a file"""
        self.f = f
        self.stack = []
        self.raw = None
        self.lineno = 0
    def pop(self):
        self.lineno += 1
        if self.stack:
            self.raw = self.stack.pop()
        else:
            self.raw = self.f.readline()
        self.stripped = self.raw.strip()
        try:
            self.parts = shlex.split(self.stripped)
        except ValueError:
            self.parts = []
    def push(self):
        self.lineno -= 1
        self.stack.append(self.raw)
    def __bool__(self):
        return self.raw is None or bool(self.raw)

def rotate_point(x, y, theta):
    x2 = x * math.cos(theta) + y * math.sin(theta)
    y2 = x * math.sin(theta) + y * math.cos(theta)
    return x2, y2

def decideg2rad(d):
    return (d/3600) * 2*math.pi

def rad2decideg(r):
    return r / 2*math.pi * 3600

def draw_text(ctx, text, posx, posy, size, hjust, vjust, theta=0):
    """Draw text onto a Cairo context.
    @param ctx - Cairo context
    @param text - string containing text to write
    @param posx - x coordinate of text origin
    @param posy - y coordinate of text origin
    @param hjust - horizontal justification relative to origin: R, C, L
    @param vjust - vertical justification relative to origin: T, C, B
    @param theta - rotation around origin
    @return BoundingBox of text
    """

    ctx.save()

    ctx.select_font_face("Courier", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(size*1.5)

    fascent, fdescent, fheight, fxadvance, fyadvance = ctx.font_extents()
    (x, y, width, height, dx, dy) = ctx.text_extents(text)

    ctx.translate(posx, posy)
    ctx.rotate(theta)
    ctx.translate(-width/2, fheight/2)

    if hjust == "R":
        sx = -width/2
        minx = -width - size
        maxx = size
    elif hjust == "C":
        sx = 0
        minx = -width/2 - size
        maxx = width/2 + size
    elif hjust == "L":
        sx = width/2
        minx = -size
        maxx = width + size
    else:
        raise ValueError("Expected R, C, or L for hjust; got %r" % hjust)

    if vjust == "T":
        sy = -height/2
        miny = -height/2
        maxy = 0
    elif vjust == "C":
        sy = 0
        miny = -height/2
        maxy = height/2
    elif vjust == "B":
        sy = height/2
        miny = 0
        maxy = height/2
    else:
        raise ValueError("Expected T, C, or B for vjust; got %r" % vjust)

    ctx.move_to(sx, sy - height/2)
    ctx.show_text(text)
    ctx.restore()

    # Rotate the bounding box
    c1 = rotate_point (minx, miny, theta)
    c2 = rotate_point (minx, maxy, theta)
    c3 = rotate_point (maxx, miny, theta)
    c4 = rotate_point (maxx, maxy, theta)
    cs = [c1, c2, c3, c4]

    minx = min(i[0] for i in cs) + posx
    maxx = max(i[0] for i in cs) + posx
    miny = min(i[1] for i in cs) + posy
    maxy = max(i[1] for i in cs) + posy

    return BoundingBox(minx, maxx, miny, maxy)

class KicadObject(object):
    def parse_line_into(self, parser, *values):
        """Parse a shlex-split line into this object's instance variables.
        @param parser - a LineParser positioned at the current line
        @param values - a list of tuples (name, converter); if name is None the
            field will be ignored.
        @return unparsed values
        """
        for field, (name, converter) in zip(parser.parts, values):
            if converter is None:
                value = field
            else:
                try:
                    value = converter(field)
                except (ValueError, TypeError):
                    raise ValueError("could not parse field %r with %s" % (field, converter))
            self.__dict__[name] = value
        return parser.parts[len(values):]

class SchSymbol(KicadObject):
    def __init__(self, stack=None):
        self.fields = []
        self.fplist = []
        self.objects = []
        self.aliases = []
        self.description = ""
        if stack is not None:
             self.parse_kicad(stack)

    @property
    def name(self):
        return self.fields[1].value

    @property
    def ref(self):
        return self.fields[0].value

    def parse_kicad(self, parser):
        """Parse a KiCad library file into this object.

        @param parser - a LineParser loaded with the file
        """

        state = "root"

        while parser:
            parser.pop()
            if not parser.raw or parser.raw.startswith("#"):
                continue
            if not parser.parts:
                raise ValueError("shlex could not parse line %d" % parser.lineno)

            if state == "root":
                if parser.parts[0] == "EESchema-LIBRARY":
                    assert parser.parts[1] == "Version"
                    assert Decimal(parser.parts[2]) <= Decimal("2.4")

                elif parser.parts[0] == "DEF":
                    self.parse_line_into(parser,
                            (None, None), # head
                            (None, None), # name
                            (None, None), # ref
                            (None, None), # unused
                            ("text_offset",     int),
                            ("draw_pinnums",    lambda x: x == "Y"),
                            ("draw_pinnames",   lambda x: x == "Y"),
                            ("n_units",         int),
                            ("units_locked",    lambda x: x == "L"),
                            ("flag",            None))

                elif parser.parts[0].startswith("F"):
                    fieldnum = int(parser.parts[0][1:])
                    assert fieldnum == len(self.fields)
                    self.fields.append(Field(self, parser))

                elif parser.parts[0] == "$FPLIST":
                    state = "fplist"

                elif parser.parts[0] == "ALIAS":
                    self.aliases.extend(parser.parts[1:])
                    
                elif parser.parts[0] == "DRAW":
                    state = "draw"

                elif parser.parts[0] == "ENDDEF":
                    return

                else:
                    print("Unrecognized line %s" % parser.parts[0], file=sys.stderr)

            elif state == "fplist":
                if parser.parts[0] == "$ENDFPLIST":
                    state = "root"
                else:
                    self.fplist.append (parser.stripped)

            elif state == "draw":
                if parser.parts[0] == "ENDDRAW":
                    state = "root"
                else:
                    objtype = {
                            "X": Pin,
                            "A": Arc,
                            "C": Circle,
                            "P": Polyline,
                            "S": Rectangle,
                            "T": Text }.get(parser.parts[0])
                    if objtype is None:
                        raise ValueError("Unrecognized graphic item %s on line %d" % (parser.parts[0], parser.lineno))
                    self.objects.append(objtype(self, parser))
            else:
                assert False, "invalid state %r" % state

    def __str__(self):
        lines = []
        lines.append(self.name + " : " + self.ref + "?")
        lines.extend(str(i) for i in self.objects)
        return '\n'.join(lines)

    def render_cairo(self, ctx, origx, origy):
        bbs = []
        for i in self.objects:
            bb = i.render_cairo(ctx, origx, origy)
            bbs.append (bb)
        return sum(bbs)

    def filter_unit(self, unit):
        self.objects = [i for i in self.objects if (i.unit == unit or i.unit == 0)]

    def filter_convert(self, convert):
        self.objects = [i for i in self.objects if (i.convert == convert or i.convert == 0)]

    def has_convert(self):
        for i in self.objects:
            if i.convert > 1:
                return True
        return False

    def sort_objects(self):
        """Sort the objects into a good drawing order"""

        def sortkey(x):
            if isinstance(x, Pin):
                return 4
            elif isinstance(x, Text):
                return 5
            elif hasattr(x, "fill") and x.fill == "F":
                return 2
            elif hasattr(x, "fill") and x.fill == "f":
                return 0
            else:
                return 1

        self.objects.sort(key=sortkey)

class Field(KicadObject):
    def __init__(self, parent, stack=None):
        self.parent = parent
        if stack is not None:
            self.parse_kicad(stack)

    def parse_kicad(self, parser):
        self.fieldname = "" # Default value
        self.parse_line_into(parser,
                (None, None), # head
                ("value",   None),
                ("posx",    int),
                ("posy",    int),
                ("size",    int),
                ("orient",  None),
                ("visible", lambda x: x == "V"),
                ("hjust",   None),
                ("vjust",   lambda x: x[0]), # CNN -> C
                ("fieldname",   None)) # Optional

    def __str__(self):
        return self.fieldname + ": " + self.value

class Pin(KicadObject):
    def __init__(self, parent, parser=None):
        self.parent = parent
        if parser is not None:
            self.parse_kicad(parser)

    def parse_kicad(self, parser):
        self.pin_type = "" # default value
        self.parse_line_into(parser,
                (None, None),   # head
                ("name",    None),
                ("num",     None),
                ("posx",    int),
                ("posy",    int),
                ("length",  int),
                ("dir",     None),
                ("num_size", int),
                ("name_size", int),
                ("unit",    int),
                ("convert", int),
                ("elec_type", None),
                ("pin_type", None))

    def __str__(self):
        return "PIN: %s (%s)" % (self.name, self.num)

    def render_cairo(self, ctx, origx, origy):
        ctx.set_line_width(MIN_WIDTH)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)

        sx = self.posx + origx
        sy = -self.posy + origy

        if self.dir in "RL":
            if self.dir == "R":
                ex = sx + self.length
                namex = ex + TEXT_OFFS + self.parent.text_offset
                namej = ("L", "C")
            else:
                ex = sx - self.length
                namex = ex - TEXT_OFFS - self.parent.text_offset
                namej = ("R", "C")
            ey = sy
            numx = (sx + ex) / 2
            numy = sy - self.num_size/2 - TEXT_OFFS
            altnumx = (sx + ex) / 2
            altnumy = sy + self.num_size/2 + TEXT_OFFS
            numth = 0
            namey = sy
            nameth = 0
        elif self.dir in "UD":
            if self.dir == "D":
                ey = sy + self.length
                namey = ey + TEXT_OFFS + self.parent.text_offset
                namej = ("R", "C")
            else:
                ey = sy - self.length
                namey = ey - TEXT_OFFS - self.parent.text_offset
                namej = ("L", "C")
            ex = sx
            numx = sx - self.num_size/2 - TEXT_OFFS
            numy = (sy + ey) / 2
            altnumx = sx + self.num_size/2 + TEXT_OFFS
            altnumy = (sy + ey) / 2
            numth = -math.pi/2
            namex = sx
            nameth = -math.pi/2

        if self.parent.text_offset == 0:
            # Pin names are on pins, not inside
            numx, altnumx = altnumx, numx
            numy, altnumy = altnumy, numy
            namex = altnumx
            namey = altnumy
            namej = ("C", "C")

        # Draw the actual pin
        ctx.move_to(sx, sy)
        ctx.line_to(ex, ey)
        ctx.set_source_rgb(*COLOR_FG)
        ctx.stroke()

        # "Inverted" bubble?
        if self.pin_type == "I":
            ctx.arc(ex, ey, 12.5, 0, 2*math.pi)

        # Endpoint
        if self.elec_type != "N":
            ctx.arc(sx, sy, 10, 0, 2*math.pi)
            ctx.stroke()

        bbs = []

        if self.num_size and self.parent.draw_pinnums:
            bbs.append(draw_text(ctx, self.num, numx, numy, self.num_size, "C", "C", numth))

        if self.name_size and self.name != "~" and self.parent.draw_pinnames:
            ctx.set_source_rgb(*COLOR_PN)
            bbs.append(draw_text(ctx, self.name, namex, namey, self.name_size, namej[0], namej[1], nameth))

        # Bounding box
        bbs.append(BoundingBox(min(sx,ex), max(sx,ex), min(sy, ey), max(sy,ey))) # Pin stick bounding box
        return sum(bbs)

class Arc(KicadObject):
    def __init__(self, parent, parser=None):
        self.parent = parent
        if parser is not None:
            self.parse_kicad(parser)

    def parse_kicad(self, parser):
        self.parse_line_into(parser,
                (None, None), # head
                ("posx",    int),
                ("posy",    int),
                ("radius",  int),
                ("start_angle", int),
                ("end_angle", int),
                ("unit",    int),
                ("convert", int),
                ("thickness", int),
                ("fill",    None),
                ("startx",  int),
                ("starty",  int),
                ("endx",    int),
                ("endy",    int))

    def __str__(self):
        return "ARC"

    def render_cairo(self, ctx, origx, origy):

        sth = -decideg2rad(self.start_angle)
        eth = -decideg2rad(self.end_angle)
        length = -eth + sth
        sth, eth = eth, sth
        if abs(length) > math.pi * 1.05:
            sth, eth = eth, sth

        posx = self.posx + origx
        posy = -self.posy + origy

        ctx.set_line_width(max(self.thickness, MIN_WIDTH))
        ctx.arc(posx, posy, self.radius, sth, eth)

        if self.fill == "F":
            ctx.set_source_rgb(*COLOR_FG)
            ctx.stroke_preserve()
            ctx.fill()
        elif self.fill == "f":
            ctx.set_source_rgb(*COLOR_FG)
            ctx.stroke_preserve()
            ctx.set_source_rgb(*COLOR_BG)
            ctx.fill()
        else:
            ctx.set_source_rgb(*COLOR_FG)
            ctx.stroke()


        minx = posx - self.radius
        maxx = posx + self.radius
        miny = posy - self.radius
        maxy = posy + self.radius
        return BoundingBox(minx, maxx, miny, maxy)

class Circle(KicadObject):
    def __init__(self, parent, parser=None):
        self.parent = parent
        if parser is not None:
            self.parse_kicad(parser)

    def parse_kicad(self, parser):
        self.parse_line_into(parser,
                (None, None),   # head
                ("posx",    int),
                ("posy",    int),
                ("radius",  int),
                ("unit",    int),
                ("convert", int),
                ("thickness", int),
                ("fill",    None))

    def __str__(self):
        return "CIRCLE"

    def render_cairo(self, ctx, origx, origy):
        ctx.set_line_width(max(self.thickness, MIN_WIDTH))

        posx = self.posx + origx
        posy = -self.posy + origy

        ctx.arc(posx, posy, self.radius, 0, 2*math.pi)

        if self.fill == "f":
            ctx.set_source_rgb(*COLOR_FG)
            ctx.stroke_preserve()
            ctx.set_source_rgb(*COLOR_BG)
            ctx.fill()
        elif self.fill == "F":
            ctx.set_source_rgb(*COLOR_FG)
            ctx.stroke_preserve()
            ctx.set_source_rgb(*COLOR_FG)
            ctx.fill()
        else:
            ctx.set_source_rgb(*COLOR_FG)
            ctx.stroke()

        minx = posx - self.radius
        maxx = posx + self.radius
        miny = posy - self.radius
        maxy = posy + self.radius
        return BoundingBox(minx, maxx, miny, maxy)


class Polyline(KicadObject):
    def __init__(self, parent, parser=None):
        self.parent = parent
        if parser is not None:
            self.parse_kicad(parser)

    def parse_kicad(self, parser):
        rest = self.parse_line_into(parser,
                (None, None),   # head
                (None, None),   # npoints
                ("unit",    int),
                ("convert", int),
                ("thickness", int))

        self.points = [(int(rest[i]), int(rest[i+1])) for i in range(0, len(rest)-1, 2)]
        self.fill = rest[-1]

    def __str__(self):
        return "POLYLINE"

    def render_cairo(self, ctx, origx, origy):
        ctx.set_line_width(max(self.thickness, MIN_WIDTH))
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        p = self.points[0]
        ctx.move_to (origx + p[0], origy - p[1])
        for p in self.points[1:]:
            ctx.line_to (origx + p[0], origy - p[1])

        if self.fill == "f":
            ctx.close_path()
            ctx.set_source_rgb(*COLOR_FG)
            ctx.stroke_preserve()
            ctx.set_source_rgb(*COLOR_BG)
            ctx.fill()
        elif self.fill == "F":
            ctx.close_path()
            ctx.set_source_rgb(*COLOR_FG)
            ctx.stroke_preserve()
            ctx.set_source_rgb(*COLOR_FG)
            ctx.fill()
        else:
            ctx.set_source_rgb(*COLOR_FG)
            ctx.stroke()

        minx = min(i[0] for i in self.points) + origx
        maxx = max(i[0] for i in self.points) + origx
        miny = min(-i[1] for i in self.points) + origy
        maxy = max(-i[1] for i in self.points) + origy
        return BoundingBox(minx, maxx, miny, maxy)

class Rectangle(KicadObject):
    def __init__(self, parent, parser=None):
        self.parent = parent
        if parser is not None:
            self.parse_kicad(parser)

    def parse_kicad(self, parser):
        self.parse_line_into(parser,
                (None, None),   # head
                ("startx",  int),
                ("starty",  int),
                ("endx",    int),
                ("endy",    int),
                ("unit",    int),
                ("convert", int),
                ("thickness",   int),
                ("fill",    None))

    def __str__(self):
        return "RECTANGLE"

    def render_cairo(self, ctx, origx, origy):
        ctx.set_line_width(max(self.thickness, MIN_WIDTH))
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)

        sx = self.startx + origx
        sy = -self.starty + origy
        ex = self.endx + origx
        ey = -self.endy + origy

        ctx.move_to(sx, sy)
        ctx.line_to(sx, ey)
        ctx.line_to(ex, ey)
        ctx.line_to(ex, sy)
        ctx.close_path()

        if self.fill == "f":
            ctx.set_source_rgb(*COLOR_FG)
            ctx.stroke_preserve()
            ctx.set_source_rgb(*COLOR_BG)
            ctx.fill()
        elif self.fill == "F":
            ctx.set_source_rgb(*COLOR_FG)
            ctx.stroke_preserve()
            ctx.set_source_rgb(*COLOR_FG)
            ctx.fill()
        else:
            ctx.set_source_rgb(*COLOR_FG)
            ctx.stroke()

        minx = min(self.startx, self.endx) + origx
        maxx = max(self.startx, self.endx) + origx
        miny = min(-self.starty, -self.endy) + origy
        maxy = max(-self.starty, -self.endy) + origy
        return BoundingBox(minx, maxx, miny, maxy)


class Text(KicadObject):
    def __init__(self, parent, parser=None):
        self.parent = parent
        if parser is not None:
            self.parse_kicad(parser)

    def parse_kicad(self, parser):
        self.parse_line_into(parser,
                (None, None),   # head
                ("direction",   int),
                ("posx",    int),
                ("posy",    int),
                ("size",    int),
                (None, None),   # unused
                ("unit",    int),
                ("convert", int),
                ("text",    lambda x: x.replace("~", " ")),
                ("italic",  lambda x: x == "Italic"),
                ("bold",    lambda x: bool(int(x))),
                ("hjust",   None),
                ("vjust",   None))

    def __str__(self):
        return "TEXT"

    def render_cairo(self, ctx, origx, origy):
        theta = (-self.direction / 10 / 360) * 2 * math.pi
        ctx.set_source_rgb(*COLOR_FG)
        return draw_text(ctx, self.text, self.posx + origx, -self.posy + origy, self.size,
                self.hjust, self.vjust, theta)

def parse_file(f):
    parser = LineParser(f)
    items = []

    while parser:
        obj = SchSymbol(parser)
        try:
            obj.name
        except IndexError:
            pass
        else:
            items.append (obj)

    return items

def get_item(items, name):
    for item in items:
        if item.name == name:
            return item

def load_dcm(items, f):
    item = None

    for line in f:
        if line.startswith("$CMP "):
            name = line.partition(" ")[2].strip()
            item = get_item(items, name)
        elif line.startswith("D ") and item is not None:
            item.description = line.partition(" ")[2].strip()
        elif line.startswith("$ENDCMP"):
            item = None

def md5sum(fn):
    return subprocess.check_output(['md5sum', fn]).decode('ascii').partition(' ')[0].strip()

if __name__ == "__main__":

    if len(sys.argv) < 4:
        print("usage: %s outdir html_dir_path cachefile libfile [dcmfile]" % sys.argv[0], file=sys.stderr)
        sys.exit(1)

    outdir = sys.argv[1]
    abs_outdir = sys.argv[2]
    cachefile = sys.argv[3]
    libfile = sys.argv[4]

    with open(libfile) as f:
        items = parse_file(f)

    # Load DCM file?
    if len(sys.argv) > 5:
        dcmfile = sys.argv[5]
        with open(dcmfile) as fdcm:
            load_dcm(items, fdcm)

    # Create a dummy Cairo context for determining bounding boxes
    dummy_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 10, 10)
    dummy_ctx = cairo.Context(dummy_surf)

    # Load the image cache
    print(cachefile, file=sys.stderr)
    if os.path.isfile(cachefile):
        try:
            with open(cachefile, "rb") as f:
                cache = pickle.load(f)
        except EOFError:
            cache = {}
    else:
        cache = {}

    libname = os.path.basename(libfile)
    assert libname.endswith(".lib")
    libname = libname[:-4]
    print("# " + libname)
    print()

    for item in items:

        print("## " + item.name)
        if item.aliases:
            print("Aliases:")
            for alias in item.aliases:
                print("* " + alias)
            print()
        if item.description:
            print(item.description)
            print()

        for unit in range(1, 1+item.n_units):
            for convert in range(1, 3 if item.has_convert() else 2):
                san_name = item.name.replace("/", "-")
                filename = "%s__%s__%d__%d.png" % (libname, san_name, unit, convert)
                relpath = os.path.join(outdir, filename)
                htmlpath = abs_outdir + "/" + filename

                itemcopy = copy.deepcopy(item)
                itemcopy.filter_unit(unit)
                itemcopy.filter_convert(convert)

                boundingbox = itemcopy.render_cairo(dummy_ctx, 0, 0)

                surf_width = boundingbox.width + 25
                surf_height = boundingbox.height + 25
                origx = surf_width/2 - boundingbox.centerx
                origy = surf_height/2 - boundingbox.centery

                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(surf_width//MILS_PER_PIXEL),
                        int(surf_height//MILS_PER_PIXEL))
                ctx = cairo.Context(surface)
                ctx.scale(1/MILS_PER_PIXEL, 1/MILS_PER_PIXEL)

                itemcopy.sort_objects()
                itemcopy.render_cairo(ctx, origx, origy)

                try:
                    surface.write_to_png(relpath)
                except OSError:
                    print(relpath, file=sys.stderr)
                    raise

                # Test if the file already exists in the cache. If it does,
                # remove the one we just wrote and substitute in the cached file
                checksum = md5sum(relpath)
                if checksum in cache:
                    os.unlink(relpath)
                    htmlpath = cache[checksum]
                else:
                    cache[checksum] = htmlpath

                print("![%s__%d__%d](%s) " % (item.name, unit, convert, htmlpath + "?raw=true"))
        print()

    # Write out the cache
    with open(cachefile, "wb") as f:
        pickle.dump(cache, f)
