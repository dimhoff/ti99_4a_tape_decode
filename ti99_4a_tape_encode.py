#!/usr/bin/env python
# ti99_4a_tape_encode.py - TI-99/4a Cassette tape data encoder
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
import pyaudio
import struct
import sys
import wave

# Length of initial sync sequence. Normally around 768, but shorter also works
# and saves time...
INITIAL_SYNC_LEN = 768

# Amount of samples per symbol at 44100 Hz sample rate
SYMBOL_LEN = 32

# Max. output level
MAX_LEVEL = 0x7fff

# Current output level
level = MAX_LEVEL

# High-pass filtering of output
use_hpf = False
last_level = level
last_filtered_value = 0

def output_write(level):
    global last_filtered_value
    global last_level

    # Filter with HPF
    if use_hpf:
        filtered_value = 0.800 * (last_filtered_value + level - last_level)
        last_filtered_value = filtered_value
        last_level = level
        level = filtered_value / 2

    # Write Sample
    sample = struct.pack("<h", level)
    if wf is not None:
        wf.writeframes(sample)
    else:
        stream.write(sample)


def write_byte(b):
    global level

    b = int(b)

    for j in xrange(0, 8):
        level = level * -1
        for i in xrange(0, int(SYMBOL_LEN / 2)):
            output_write(level)

        if b & 0x80:
            level = level * -1

        for i in xrange(0, int(SYMBOL_LEN / 2)):
            output_write(level)

        b = b << 1

if len(sys.argv) < 2 or len(sys.argv) > 3:
    print("Usage: %s input.dat [output.wav]" % sys.argv[0])
    print("")
    print("if no output file is specified the default audio output is used")
    exit(1)

with open(sys.argv[1], "rb") as ifile:
    data = ifile.read()
    print("Encoding {} bytes of data".format(len(data)))
    padding = 64 - (len(data) % 64)
    if padding != 64:
        data += '\x80' * padding

nrecords = int(math.ceil(len(data) / 64))
if nrecords > 0xff:
    print("Too many records: {}".format(nrecords))
    exit(1)
# TODO: pad to multiple of 64

# Open output
wf = None
if len(sys.argv) == 3:
    wf = wave.open(sys.argv[2], 'wb')
    wf.setsampwidth(2)
    wf.setnchannels(1)
    wf.setframerate(44100)
else:
    p = pyaudio.PyAudio()

    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=44100,
                    input=False,
                    output=True)

    stream.start_stream()

    # Fill buffer to prevent underruns in the beginning
    stream.write("\x00\x00" * 50000)

# Send Sync
for i in xrange(0, INITIAL_SYNC_LEN):
    write_byte(0x00)

# Send header
print("Writing header, Total # records {}".format(nrecords))
write_byte(0xff)
write_byte(nrecords)
write_byte(nrecords)

# Send records
for i in xrange(0, nrecords):
    print("Writing Record {}".format(i))
    for z in xrange(0, 2):
        for j in xrange(0, 8):
            write_byte(0x00)

        write_byte(0xff)

        chksum = 0
        for j in xrange(0, 64):
            b = ord(data[(i * 64) + j])
            chksum += b
            write_byte(b)

        write_byte(chksum)

# Close output
if wf is not None:
    wf.close()
else:
    stream.stop_stream()
    stream.close()

    p.terminate()
