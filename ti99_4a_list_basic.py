#!/usr/bin/env python
# ti99_4a_list_basic.py - List TI-99/4a BASIC tape dump program
#
# Copyright (c) 2016 David Imhoff <dimhoff.devel@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
#
# Based on the information found on:
#   http://www.ninerpedia.org/index.php?title=BASIC_file_formats
#
import struct
import sys

# TODO:
#  - Must be a better way to determine addresses in parse_line_table()

TOKENS = {
    0x00: ('NEW ', 0, 'all'),
    0x01: ('CON(TINUE) ', 0, 'all'),
    0x02: ('LIST ', 0, 'all'),
    0x03: ('BYE ', 0, 'all'),
    0x04: ('NUM(BER) ', 0, 'all'),
    0x05: ('OLD ', 0, 'all'),
    0x06: ('RES(EQUENCE) ', 0, 'all'),
    0x07: ('SAVE ', 0, 'all'),
    0x08: ('MERGE ', 0, 'Extended BASIC'),
    0x09: ('EDIT ', 0, 'TI BASIC '),

    0x81: ('ELSE ', 0, 'all'),
    0x82: (' :: ', 0, 'Extended BASIC'),
    0x83: (' ! ', 0, 'Extended BASIC'),
    0x84: ('IF ', 0, 'all'),
    0x85: ('GO ', 0, 'all'),
    0x86: ('GOTO ', 0, 'all'),
    0x87: ('GOSUB ', 0, 'all'),
    0x88: ('RETURN ', 0, 'all'),
    0x89: ('DEF ', 0, 'all'),
    0x8a: ('DIM ', 0, 'all'),
    0x8b: ('END ', 0, 'all'),
    0x8c: ('FOR ', 0, 'all'),
    0x8d: ('LET ', 0, 'all'),
    0x8e: ('BREAK ', 0, 'all'),
    0x8f: ('UNBREAK ', 0, 'all'),
    0x90: ('TRACE ', 0, 'all'),
    0x91: ('UNTRACE ', 0, 'all'),
    0x92: ('INPUT ', 0, 'all'),
    0x93: ('DATA ', 0, 'all'),
    0x94: ('RESTORE ', 0, 'all'),
    0x95: ('RANDOMIZE ', 0, 'all'),
    0x96: ('NEXT ', 0, 'all'),
    0x97: ('READ ', 0, 'all'),
    0x98: ('STOP ', 0, 'all'),
    0x99: ('DELETE ', 0, 'all'),
    0x9a: ('REM ', 0, 'all'),
    0x9b: ('ON ', 0, 'all'),
    0x9c: ('PRINT ', 0, 'all'),
    0x9d: ('CALL ', 0, 'all'),
    0x9e: ('OPTION ', 0, 'all'),
    0x9f: ('OPEN ', 0, 'all'),
    0xa0: ('CLOSE ', 0, 'all'),
    0xa1: ('SUB ', 0, 'all (after GO), Extended BASIC'),
    0xa2: ('DISPLAY ', 0, 'all'),
    0xa3: ('IMAGE ', 0, 'Extended BASIC'),
    0xa4: ('ACCEPT ', 0, 'Extended BASIC'),
    0xa5: ('ERROR ', 0, 'Extended BASIC'),
    0xa6: ('WARNING ', 0, 'Extended BASIC'),
    0xa7: ('SUBEXIT ', 0, 'Extended BASIC'),
    0xa8: ('SUBEND ', 0, 'Extended BASIC'),
    0xa9: ('RUN ', 0, 'all'),
    0xaa: ('LINPUT ', 0, 'Extended BASIC'),
    0xb0: ('THEN ', 0, 'all'),
    0xb1: ('TO ', 0, 'all'),
    0xb2: ('STEP ', 0, 'all'),
    0xb3: (', ', 0, 'all'),
    0xb4: (' ; ', 0, 'all'),
    0xb5: (' : ', 0, 'all'),
    0xb6: (') ', 0, 'all'),
    0xb7: ('(', 0, 'all'),
    0xb8: ('& ', 0, 'all'),
    0xba: ('OR ', 0, 'Extended BASIC'),
    0xbb: ('AND ', 0, 'Extended BASIC'),
    0xbc: ('XOR ', 0, 'Extended BASIC'),
    0xbd: ('NOT ', 0, 'Extended BASIC'),
    0xbe: ('= ', 0, 'all'),
    0xbf: ('< ', 0, 'all'),
    0xc0: ('> ', 0, 'all'),
    0xc1: ('+ ', 0, 'all'),
    0xc2: ('- ', 0, 'all'),
    0xc3: ('* ', 0, 'all'),
    0xc4: ('/ ', 0, 'all'),
    0xc5: ('^ ', 0, 'all'),
    0xc7: ('Quoted string ', -1, 'all'),
    0xc8: ('Unquoted string ', -1, 'all'),
    0xc9: ('Line number ', 0, 'all'),
    0xca: ('EOF ', 0, 'all'),
    0xcb: ('ABS ', 0, 'all'),
    0xcc: ('ATN ', 0, 'all'),
    0xcd: ('COS ', 0, 'all'),
    0xce: ('EXP ', 0, 'all'),
    0xcf: ('INT ', 0, 'all'),
    0xd0: ('LOG ', 0, 'all'),
    0xd1: ('SGN ', 0, 'all'),
    0xd2: ('SIN ', 0, 'all'),
    0xd3: ('SQR ', 0, 'all'),
    0xd4: ('TAN ', 0, 'all'),
    0xd5: ('LEN ', 0, 'all'),
    0xd6: ('CHR$ ', 0, 'all'),
    0xd7: ('RND ', 0, 'all'),
    0xd8: ('SEG$ ', 0, 'all'),
    0xd9: ('POS ', 0, 'all'),
    0xda: ('VAL ', 0, 'all'),
    0xdb: ('STR$ ', 0, 'all'),
    0xdc: ('ASC ', 0, 'all'),
    0xdd: ('PI ', 0, 'Extended BASIC'),
    0xde: ('REC ', 0, 'all'),
    0xdf: ('MAX ', 0, 'Extended BASIC'),
    0xe0: ('MIN ', 0, 'Extended BASIC'),
    0xe1: ('RPT$ ', 0, 'Extended BASIC'),
    0xe8: ('NUMERIC ', 0, 'Extended BASIC'),
    0xe9: ('DIGIT ', 0, 'Extended BASIC'),
    0xea: ('UALPHA ', 0, 'Extended BASIC'),
    0xeb: ('SIZE ', 0, 'Extended BASIC'),
    0xec: ('ALL ', 0, 'Extended BASIC'),
    0xed: ('USING ', 0, 'Extended BASIC'),
    0xee: ('BEEP ', 0, 'Extended BASIC'),
    0xef: ('ERASE ', 0, 'Extended BASIC'),
    0xf0: ('AT ', 0, 'Extended BASIC'),
    0xf1: ('BASE ', 0, 'all'),
    0xf3: ('VARIABLE ', 0, 'all'),
    0xf4: ('RELATIVE ', 0, 'all'),
    0xf5: ('INTERNAL ', 0, 'all'),
    0xf6: ('SEQUENTIAL ', 0, 'all'),
    0xf7: ('OUTPUT ', 0, 'all'),
    0xf8: ('UPDATE ', 0, 'all'),
    0xf9: ('APPEND ', 0, 'all'),
    0xfa: ('FIXED ', 0, 'all'),
    0xfb: ('PERMANENT ', 0, 'all'),
    0xfc: ('TAB ', 0, 'all'),
    0xfd: ('# ', 0, 'all'),
    0xfe: ('VALIDATE ', 0, 'Extended BASIC '),
}

HDR_LEN = 8


def parse_header(data):
    if len(data) < HDR_LEN:
        print("ERROR: data to small to fit header")
        exit(1)

    (chkword, line_table_start, line_table_end,
        memory_end) = struct.unpack_from('>HHHH', data, 0)

    if line_table_start ^ line_table_end != chkword & 0x7fff:
        print("header checksum failure")
        return None

    return {
        'chkword': chkword,
        'line_table_start': line_table_start,
        'line_table_end': line_table_end,
        'memory_end': memory_end,
    }


def parse_line_table(data, header):
    # NOTE: End points to the last byte and not one beyond
    lt_len = header['line_table_start'] + 1 - header['line_table_end']

    if lt_len + HDR_LEN > len(data):
        print("ERROR: Line table length to big for data")
        exit(1)

    if lt_len % 4:
        print("ERROR: Line table length not multiple of 4")
        exit(1)

    # NOTE: LT memory grows down, so start > end...
    lt = {}
    for i in range(0, lt_len, 4):
        entry = struct.unpack_from(">HH", data, HDR_LEN + lt_len - 4 - i)

        lt[entry[0]] = (entry[1] - (header['line_table_start'] + 1) + HDR_LEN +
                        lt_len)

        # NOTE: The LT entry address point to the beginning of the line data.
        #       NOT to the length byte preceding the line.
        lt[entry[0]] -= 1

    return lt


class DecodeException(Exception):
    pass


def decode_line(data, addr):

    line_len = data[addr]

    if addr + line_len >= len(data):
        raise DecodeException("Line length beyond end of data")

    if chr(data[addr + line_len]) != '\x00':
        raise DecodeException("DECODE ERROR: Invalid EOL byte")

    line = ''
    off = 1
    while off < line_len:
        token = data[addr + off]
        off += 1

        if token == 0x81:
            line = line + 'ELSE '
        elif token == 0x82:
            line = line + ' :: '
        elif token == 0x83:
            line = line + ' ! '
            line = line + data[addr + off:addr + line_len].decode(encoding='latin-1')
            off = line_len
        elif token == 0x84:
            line = line + 'IF '
        elif token == 0x85:
            line = line + 'GO '
        elif token == 0x86:
            line = line + 'GOTO '
        elif token == 0x87:
            line = line + 'GOSUB '
        elif token == 0x88:
            line = line + 'RETURN '
        elif token == 0x89:
            line = line + 'DEF '
        elif token == 0x8a:
            line = line + 'DIM '
        elif token == 0x8b:
            line = line + 'END '
        elif token == 0x8c:
            line = line + 'FOR '
        elif token == 0x8d:
            line = line + 'LET '
        elif token == 0x8e:
            line = line + 'BREAK '
        elif token == 0x8f:
            line = line + 'UNBREAK '
        elif token == 0x90:
            line = line + 'TRACE '
        elif token == 0x91:
            line = line + 'UNTRACE '
        elif token == 0x92:
            line = line + 'INPUT '
        elif token == 0x93:
            line = line + 'DATA '
        elif token == 0x94:
            line = line + 'RESTORE '
        elif token == 0x95:
            line = line + 'RANDOMIZE '
        elif token == 0x96:
            line = line + 'NEXT '
        elif token == 0x97:
            line = line + 'READ '
        elif token == 0x98:
            line = line + 'STOP '
        elif token == 0x99:
            line = line + 'DELETE '
        elif token == 0x9a:
            line = line + 'REM '
            line = line + data[addr + off:addr + line_len].decode(encoding='latin-1')
            off = line_len
        elif token == 0x9b:
            line = line + 'ON '
        elif token == 0x9c:
            line = line + 'PRINT '
        elif token == 0x9d:
            line = line + 'CALL '
        elif token == 0x9e:
            line = line + 'OPTION '
        elif token == 0x9f:
            line = line + 'OPEN '
        elif token == 0xa0:
            line = line + 'CLOSE '
        elif token == 0xa1:
            line = line + 'SUB '
        elif token == 0xa2:
            line = line + 'DISPLAY '
        elif token == 0xa3:
            line = line + 'IMAGE '
        elif token == 0xa4:
            line = line + 'ACCEPT '
        elif token == 0xa5:
            line = line + 'ERROR '
        elif token == 0xa6:
            line = line + 'WARNING '
        elif token == 0xa7:
            line = line + 'SUBEXIT '
        elif token == 0xa8:
            line = line + 'SUBEND '
        elif token == 0xa9:
            line = line + 'RUN '
        elif token == 0xaa:
            line = line + 'LINPUT '
        elif token == 0xb0:
            line = line + 'THEN '
        elif token == 0xb1:
            line = line + 'TO '
        elif token == 0xb2:
            line = line + 'STEP '
        elif token == 0xb3:
            line = line + ', '
        elif token == 0xb4:
            line = line + ' ; '
        elif token == 0xb5:
            line = line + ' : '
        elif token == 0xb6:
            line = line + ') '
        elif token == 0xb7:
            line = line + '( '
        elif token == 0xb8:
            line = line + '& '
        elif token == 0xba:
            line = line + 'OR '
        elif token == 0xbb:
            line = line + 'AND '
        elif token == 0xbc:
            line = line + 'XOR '
        elif token == 0xbd:
            line = line + 'NOT '
        elif token == 0xbe:
            line = line + '= '
        elif token == 0xbf:
            line = line + '< '
        elif token == 0xc0:
            line = line + '> '
        elif token == 0xc1:
            line = line + '+ '
        elif token == 0xc2:
            line = line + '- '
        elif token == 0xc3:
            line = line + '* '
        elif token == 0xc4:
            line = line + '/ '
        elif token == 0xc5:
            line = line + '^ '
        elif token == 0xc7:
            if off + 1 > line_len:
                raise DecodeException("Quoted str. argument beyond EOL")

            arg_len = data[addr + off]
            off += 1

            if off + arg_len > line_len:
                raise DecodeException("Quoted str. argument beyond EOL")

            line = line + '"' + data[addr + off:addr + off + arg_len].decode(encoding='latin-1') + '" '
            off += arg_len
        elif token == 0xc8:
            if off + 1 > line_len:
                raise DecodeException("Unquoted str. argument beyond EOL")

            arg_len = data[addr + off]
            off += 1

            if off + arg_len > line_len:
                raise DecodeException("Unquoted str. argument beyond EOL")

            line = line + data[addr + off:addr + off + arg_len].decode(encoding='latin-1') + ' '
            off += arg_len
        elif token == 0xc9:
            if off + 2 > line_len:
                raise DecodeException("line # argument beyond EOL")
            arg = struct.unpack_from(">h", data, addr + off)[0]
            line = line + str(arg)
            off += 2
        elif token == 0xca:
            line = line + 'EOF '
        elif token == 0xcb:
            line = line + 'ABS '
        elif token == 0xcc:
            line = line + 'ATN '
        elif token == 0xcd:
            line = line + 'COS '
        elif token == 0xce:
            line = line + 'EXP '
        elif token == 0xcf:
            line = line + 'INT '
        elif token == 0xd0:
            line = line + 'LOG '
        elif token == 0xd1:
            line = line + 'SGN '
        elif token == 0xd2:
            line = line + 'SIN '
        elif token == 0xd3:
            line = line + 'SQR '
        elif token == 0xd4:
            line = line + 'TAN '
        elif token == 0xd5:
            line = line + 'LEN '
        elif token == 0xd6:
            line = line + 'CHR$ '
        elif token == 0xd7:
            line = line + 'RND '
        elif token == 0xd8:
            line = line + 'SEG$ '
        elif token == 0xd9:
            line = line + 'POS '
        elif token == 0xda:
            line = line + 'VAL '
        elif token == 0xdb:
            line = line + 'STR$ '
        elif token == 0xdc:
            line = line + 'ASC '
        elif token == 0xdd:
            line = line + 'PI '
        elif token == 0xde:
            line = line + 'REC '
        elif token == 0xdf:
            line = line + 'MAX '
        elif token == 0xe0:
            line = line + 'MIN '
        elif token == 0xe1:
            line = line + 'RPT$ '
        elif token == 0xe8:
            line = line + 'NUMERIC '
        elif token == 0xe9:
            line = line + 'DIGIT '
        elif token == 0xea:
            line = line + 'UALPHA '
        elif token == 0xeb:
            line = line + 'SIZE '
        elif token == 0xec:
            line = line + 'ALL '
        elif token == 0xed:
            line = line + 'USING '
        elif token == 0xee:
            line = line + 'BEEP '
        elif token == 0xef:
            line = line + 'ERASE '
        elif token == 0xf0:
            line = line + 'AT '
        elif token == 0xf1:
            line = line + 'BASE '
        elif token == 0xf3:
            line = line + 'VARIABLE '
        elif token == 0xf4:
            line = line + 'RELATIVE '
        elif token == 0xf5:
            line = line + 'INTERNAL '
        elif token == 0xf6:
            line = line + 'SEQUENTIAL '
        elif token == 0xf7:
            line = line + 'OUTPUT '
        elif token == 0xf8:
            line = line + 'UPDATE '
        elif token == 0xf9:
            line = line + 'APPEND '
        elif token == 0xfa:
            line = line + 'FIXED '
        elif token == 0xfb:
            line = line + 'PERMANENT '
        elif token == 0xfc:
            line = line + 'TAB '
        elif token == 0xfd:
            line = line + '# '
        elif token == 0xfe:
            line = line + 'VALIDATE '
        elif (ord('A') <= token <= ord('Z') or
                ord('a') <= token <= ord('z') or
                token == ord('\\') or token == ord('[') or token == ord(']') or
                token == ord('_') or token == ord('@')):
            # NOTE: '\[]' aren't allowed according to my manual for TI-99/4,
            #       but they work...
            line = line + chr(token)

            next_char = chr(data[addr + off])
            while ('A' <= next_char <= 'Z' or
                    'a' <= next_char <= 'z' or
                    '0' <= next_char <= '9' or
                    token == '\\' or token == '[' or token == ']' or
                    next_char == '$' or
                    next_char == '_' or next_char == '@'):
                off += 1
                line = line + next_char
                if next_char == '$':
                    break
                next_char = chr(data[addr + off])
            line = line + ' '
        else:
            print(line)
            print(data[addr:addr+line_len].encode('hex'))
            raise DecodeException("Invalid token 0x{:02x}".format(token))

    return line


with open(sys.argv[1], 'rb') as inp:
    data = inp.read()

header = parse_header(data)

# print("Header:")
# print(" - Line table start: 0x{:04x}".format(header['line_table_start']))
# print(" - Line table end: 0x{:04x}".format(header['line_table_end']))
# print(" - Memory end: 0x{:04x}".format(header['memory_end']))
# if header['chkword'] & 0x8000:
#     print(" - Program is protected (ExBas)")
# print("")

lt = parse_line_table(data, header)
for line in sorted(lt):
    print("{:5} {}".format(line, decode_line(data, lt[line])))
