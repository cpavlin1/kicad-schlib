# KiCad schematic library module

# Written by Chris Pavlina
# CC0 1.0 Universal

import shlex

class FileReader(object):
    """Simple line-oriented file reader that tracks line numbers for error reporting."""

    def __init__(self, f):
        self.f = f
        self.stack = []
        self.line_number = 0

    def readline(self):
        if self.stack:
            self.line_number += 1
            return self.stack.pop()
        else:
            line = self.f.readline()
            if line != "":
                self.line_number += 1
            return line

    def putback(self, line):
        self.stack.append(line)
        self.line_number -= 1

class KiSyntaxError(Exception):
    def __init__(self, line_number, msg):
        self.line_number = line_number
        self.msg = msg

    def __str__(self):
        return "Library syntax error, line %d: %s" % (self.line_number, self.msg)

class Library(object):
    def __init__(self, parts):
        self.parts = parts

    @classmethod
    def parse(cls, reader):
        line = reader.readline()
        if not line.startswith("EESchema-LIBRARY Version "):
            raise KiSyntaxError(reader.line_number, "Expected \"EESchema-LIBRARY\"")
        version = line.split()[2]
        if not version in ("2.3", "2.4"):
            raise KiSyntaxError(reader.line_number, "Expected file format version 2.3 or 2.4")

        line = reader.readline()
        if not line.startswith("#encoding "):
            raise KiSyntaxError(reader.line_number, "Expected encoding")
        if line != "#encoding utf-8\n":
            raise KiSyntaxError(reader.line_number, "Expected encoding utf-8")

        parts = []
        while True:
            part = Part.parse(reader)
            if part is None:
                break
            else:
                parts.append(part)

        return Library(parts)

class Part(object):
    def __init__(self):
        self.fields = []
        self.fp_filters = []
        self.aliases = []
        self.drawings = []

    @property
    def name(self):
        return self.fields[1].value
    @name.setter
    def name(self, v):
        self.fields[1].value = v
        self.def_name = v

    @property
    def reference(self):
        return self.fields[0].value
    @reference.setter
    def reference(self, v):
        self.fields[0].value = v
        self.def_reference = v

    @property
    def footprint(self):
        return self.fields[2].value
    @footprint.setter
    def footprint(self, v):
        self.fields[2].value = v

    @property
    def datasheet(self):
        return self.fields[3].value
    @datasheet.setter
    def datasheet(self, v):
        self.fields[3].value = v

    def field(self, name):
        for i in self.fields:
            if i.name == name:
                return i
        raise KeyError(name)

    def parse_def(self, line):
        data = line.split()
        assert len(data) == 10
        assert data[0] == "DEF"
        self.def_name = data[1]
        self.def_reference = data[2]
        # data[3] is "reserved"
        self.text_offset = int(data[4])
        self.draw_pin_number = (data[5] == "Y")
        self.draw_pin_name = (data[6] == "Y")
        self.unit_count = int(data[7])
        self.units_locked = (data[8] == "L")
        self.is_power = (data[9] == "P")

    def parse_field(self, line):
        data = line.split()
        assert len(data) >= 9
        assert data[0][0] == "F"

    def parse_fplist(self, reader):
        while True:
            line = reader.readline()
            if line == "$ENDFPLIST\n":
                break
            elif line == "":
                raise KiSyntaxError(reader.line_number, "EOF before $ENDFPLIST")
            elif line[0] != " ":
                raise KiSyntaxError(reader.line_number, "Footprint filter must start with ' '")
            else:
                self.fp_filters.append(line.strip())

    @classmethod
    def parse(cls, reader):

        part = None

        while True:
            line = reader.readline()

            if line.startswith("#"):
                continue

            elif line.startswith("DEF"):
                try:
                    part = cls()
                    part.parse_def(line)
                except Exception as e:
                    part = None
                    raise KiSyntaxError(reader.line_number, "Invalid DEF line") from e

            elif line.startswith("F"):
                try:
                    part.fields.append(Field().parse(line))
                    field = Field().parse(line)
                except Exception as e:
                    raise KiSyntaxError(reader.line_number, "Invalid field") from e

            elif line == "$FPLIST\n":
                try:
                    part.parse_fplist(reader)
                except Exception as e:
                    raise KiSyntaxError(reader.line_number, "Invalid FPLIST") from e

            elif line.startswith("ALIAS "):
                data = line.split()
                part.aliases.extend(data[1:])

            elif line == "DRAW\n":
                part.drawings.extend(Drawing.parse(reader))

            elif line == "ENDDEF\n":
                return part

            elif line == "" and part is not None:
                raise KiSyntaxError(reader.line_number, "EOF before ENDDEF")

            elif line == "":
                return None

            else:
                raise KiSyntaxError(reader.line_number, "Unknown line type")

class Drawing(object):
    @classmethod
    def parse(cls, reader):

        types = {
            "A": Arc,
            "C": Circle,
            "P": Polyline,
            "S": Rectangle,
            "T": Text,
            "X": Pin,
                }

        drawings = []
        while True:
            line = reader.readline()
            if line == "":
                raise KiSyntaxError(reader.line_number, "EOF before ENDDRAW")

            elif line == "ENDDRAW\n":
                return drawings

            elif line[0] in types:
                try:
                    drawings.append(types[line[0]]().parse(line))
                except Exception as e:
                    raise KiSyntaxError(reader.line_number, "Invalid graphic item")

class Arc(Drawing):
    def parse(self, line):
        data = line.split()
        assert data[0] == "A"
        self.posx = int(data[1])
        self.posy = int(data[2])
        self.radius = int(data[3])
        self.start_angle = int(data[4])
        self.end_angle = int(data[5])
        self.unit = int(data[6])
        self.convert = int(data[7])
        self.thickness = int(data[8])
        self.fill = data[9]
        return self

class Circle(Drawing):
    def parse(self, line):
        data = line.split()
        assert data[0] == "C"
        self.posx = int(data[1])
        self.posy = int(data[2])
        self.radius = int(data[3])
        self.unit = int(data[4])
        self.convert = int(data[5])
        self.thickness = int(data[6])
        self.fill = data[7]
        return self

class Polyline(Drawing):
    def parse(self, line):
        data = line.split()
        assert data[0] == "P"
        point_count = int(data[1])
        self.unit = int(data[2])
        self.convert = int(data[3])
        self.thickness = int(data[4])
        self.fill = data[-1]
        points_data = data[5:-1]
        assert len(points_data) % 2 == 0
        self.points = [(points_data[i], points_data[i+1]) for i in range(0, len(points_data), 2)]
        assert point_count == len(self.points)
        return self

class Rectangle(Drawing):
    def parse(self, line):
        data = line.split()
        assert data[0] == "S"
        self.startx = int(data[1])
        self.starty = int(data[2])
        self.endx = int(data[3])
        self.endy = int(data[4])
        self.unit = int(data[5])
        self.convert = int(data[6])
        self.thickness = int(data[7])
        self.fill = data[8]
        return self

class Text(Drawing):
    def parse(self, line):
        data = line.split()
        if data[8].startswith('"'):
            # Quoted text, parse differently
            data = shlex.split(line)
        else:
            # Non-quoted uses ~ as space
            data[8] = data[8].replace("~", " ")

        assert data[0] == "T"
        self.direction = int(data[1])
        self.posx = int(data[2])
        self.posy = int(data[3])
        self.size = int(data[4])
        self.hidden = (int(data[5]) == 1)
        self.unit = int(data[6])
        self.convert = int(data[7])
        self.text = data[8]
        self.italic = (data[9] == "Italic")
        self.bold = (int(data[10]) == 1)
        self.hjustify = data[11]
        self.vjustify = data[12]
        return self

class Pin(Drawing):
    def parse(self, line):
        data = line.split()
        assert data[0] == "X"
        self.name = data[1]
        self.number = data[2]
        self.posx = int(data[3])
        self.posy = int(data[4])
        self.length = int(data[5])
        self.direction = data[6]
        self.name_size = int(data[7])
        self.number_size = int(data[8])
        self.unit = int(data[9])
        self.convert = int(data[10])
        self.elec_type = data[11]
        if len(data) >= 13:
            self.pin_type = data[12]
        else:
            self.pin_type = ""
        return self

class Field(object):
    def parse(self, line):
        data = shlex.split(line)
        assert data[0][0] == "F"
        self.num = int(data[0][1:])
        self.value = data[1]
        if self.value == "~":
            self.value = ""
        self.posx = int(data[2])
        self.posy = int(data[3])
        self.size = int(data[4])
        self.orient = data[5]
        self.visible = (data[6] == "V")
        self.hjustify = data[7]

        # data[8] is weird...
        self.vjustify = data[8][0]
        if len(data[8]) == 3:
            self.italic = (data[8][1] == "I")
            self.bold = (data[8][2] == "B")
        elif len(data[8]) == 1:
            self.italic = False
            self.bold = False
        else:
            raise ValueError("Invalid field length for vjust/style")

        if len(data) >= 10:
            self.name = data[9]
        else:
            self.name = self.num
        return self
