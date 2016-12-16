#!/usr/bin/env python
# raw_to_tifile.py - Convert raw TI-99/4a tape dump to TIFILE format
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
import math
import struct
import sys

SECT_LEN = 256

input_file = sys.argv[1]

filename = 'TESTFILE'
output_file = filename + '.tifile'

with open(input_file, 'rb') as inf:
    data = inf.read()

sect_cnt = int(math.ceil(float(len(data)) / SECT_LEN))
eof_off = len(data) % SECT_LEN
timestamp_now = '\x00\x00\x00\x00'  # TODO:
print("{}%{}={}".format(len(data), SECT_LEN, eof_off))

file_header = (
    "\x07TIFILES" +                     # File Magic
    struct.pack(">H", sect_cnt) +       # Tot. Num. Sectors
    "\x01" +                            # Flags: Program
    "\x00" +                            # Num. Rec./Sect.
    struct.pack(">B", eof_off) +        # EOF offset
    "\x00" +                            # Logical Record Length
    "\x00\x00" +                        # L3 Record Count
    filename.ljust(10, ' ')[:10] +      # File name
    "\x00" +                            # MXT, 0 == last file
    "\x00" +                            # --Reserved--
    "\x00\x00" +                        # No extended headers
    timestamp_now +                     # Creation Time
    timestamp_now +                     # Update Time
    ('\x00' * 90))                      # Padding

with open(output_file, 'wb') as outf:
    outf.write(file_header)
    outf.write(data)
    if eof_off:
        outf.write('\x00' * (SECT_LEN - eof_off))
