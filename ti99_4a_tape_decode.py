#!/usr/bin/env python3
# ti99_4a_tape_decode.py - TI-99/4a cassette tape decoder
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
import argparse
import math
import pyaudio
import time
import struct
import sys
import traceback
import wave

VERSION_MAJOR = "0"
VERSION_MINOR = "0"

# TODO:
# - Single edge/peak decoding
# - Be able to detect last bit of data when using peak detection

###############################################################################
# Configuration profiles
###

# Parameter configuration profiles.
# The following configuration items are available:
# - description:
#   Profile description string. This is for documentation/help function.
#
# - use_peak:
#   Determine symbol lengths based on peak detection rather than edge detection
#
# - training_threshold:
#   Minimum subsequent 0 bit to consider training complete
#   NOTE: Use a rather big number to make sure the audio volume normilazation
#         on some tapes is done before exiting training mode
#   NOTE: By using a threshold > (64 + 1 + 1) * 2 should guarantee we don't
#         trigger on a record. The times two is to prevent an all 1 record
#         from triggering the training.
#
# - min_bit_len:
#   Minimum absolute length of a bit
#   TODO: replace by using an expected symbol len
#
# - hysteresis:
#   Hysteresis factor of dynamic range
#
# - max_bit_diff:
#   Max. Deviation of bit width in percent / 100
#
# - range_decay:
#   Factor with which the dynamic range tops decay per sample
#
# - continues_resync:
#   Resync on every symbol border
#   FIXME: currently required due to the lack of inter record training
#
profiles = {
    'peak1': {
        'description': "Basic peak detection based decoder",
        'use_peak': True,
        'training_threshold': 400,
        'min_bit_len': 10,
        'hysteresis':  0.50,
        'max_bit_diff': 0.24,
        'range_decay': 0.990,
        'continues_resync': True,
    },
    'edge1': {
        'description': "Basic edge detection based decoder",
        'use_peak': False,
        'training_threshold': 400,
        'min_bit_len': 10,
        'hysteresis':  0.80,
        'max_bit_diff': 0.24,
        'range_decay': 0.995,
        'continues_resync': True,
    },
}
DEFAULT_PROFILE = 'peak1'

###############################################################################
# Constants
###
# Number of initial synchronization '0' bits the data starts with
# NOTE: This is a little bit higher than the actual value, but some of my tapes
#       seem to use a bit more... anyway it doesn't matter that much...
MAX_INITIAL_SYNC_SYMBOLS = 800 * 8

# Number of synchronization '0' bits between records
MAX_RECORD_SYNC_SYMBOLS = 8 * 8

# Number of symbols at end of synchronization period (eg. 0xff byte after the
# eight 0 bytes)
END_OF_SYNC_SYMBOLS = 8

# Record length
RECORD_LEN = 64

# Record checksum length
CHKSUM_LEN = 1

###############################################################################
# DEBUG STUFF
###
DEBUG_BITS = False
DEBUG_RESYNC_BITS = False

debug_frame_idx = 0


def debug_print(msg):
    print("{: 10}: {}".format(debug_frame_idx, msg))


###############################################################################
# Process Data bytes
###

class DataProcIface(object):
    REQUEST_RESYNC = 'SYNC'
    NOTIFY_DONE = 'DONE'

    def process_byte(self, val, bit_error_mask):
        """Called for every received byte. This function can return one
        of the following constants to notify the lower layer.

         - REQUEST_RESYNC: Start signal resynchronization
         - NOTIFY_DONE: Indicate that reception of current program is
                        finished. Lower layer will wait for a new header.
        """
        pass

    def resync_failed_cb(self):
        """Called if resync failed before max. symbols is reached. If
        this funtion returns True lower layer will skip the current
        record and will try to resync on the next record. If False is
        returned then lower layer will stop proccessing the current
        program."""
        pass

    def process_eof(self):
        """Called upon end of input is reached"""
        pass


class DataProc(DataProcIface):
    def __init__(self, file_prefix=None, file_extension=None):
        self.__clear_state()

        if file_prefix is not None:
            self.__file_prefix = file_prefix
        else:
            self.__file_prefix = "tape_"

        if file_extension is not None:
            self.__file_extension = file_extension
        else:
            self.__file_extension = 'dat'

        self.__file_idx = 0

    def __clear_state(self):
        self.__buf = ''
        self.__buf_error_mask = ''

        self.__read_header = True
        self.__rec_cnt = 0
        self.__rec_idx = 0
        self.__rec_primary = True
        self.__rec_processed = False

        self.__data_corrupt = False
        self.__data = ''

    def process_byte(self, val, bit_error_mask):
        self.__buf += chr(val)
        self.__buf_error_mask += chr(bit_error_mask)

        if self.__read_header:
            return self._process_header()
        elif len(self.__buf) == RECORD_LEN + CHKSUM_LEN:
            return self._process_record()

    def _process_header(self):
        if len(self.__buf) == 2:
            if self.__buf[0] != self.__buf[1]:
                debug_print("ERROR: Header record count mismatch")
                debug_print("----------------------------------")
                self.__clear_state()
                return DataProcIface.NOTIFY_DONE

            self.__rec_cnt = ord(self.__buf[0])
            self.__rec_idx = 0
            self.__read_header = False
            self.__buf = ''

            debug_print("Successfully parsed header; rec count = {}".format(
                            self.__rec_cnt))

            return DataProcIface.REQUEST_RESYNC

    def _process_record(self):
        if self.__buf:
            record_data = self.__buf[0:-1]

            record_valid = True
            if not self.__verify_record():
                debug_print("WARNING: record {}{} incorrect checksum".format(
                    self.__rec_idx + 1, 'a' if self.__rec_primary else 'b'))
                record_valid = False
        else:
            debug_print("WARNING: record {}{} synchronization failed".format(
                self.__rec_idx + 1, 'a' if self.__rec_primary else 'b'))
            record_valid = False

        if self.__rec_primary:
            if record_valid:
                self.__data += record_data
                self.__rec_processed = True
            else:
                self.__rec_primary_buf = self.__buf
                self.__rec_primary_error_mask = self.__buf_error_mask

            self.__rec_primary = False
        else:
            record_corrupt = False
            if not self.__rec_processed:
                if record_valid:
                    self.__data += record_data
                else:
                    if not self.__recover_record():
                        debug_print("ERROR: Record {:2} both primary and "
                                    "secondary records corrupted".format(
                                        self.__rec_idx + 1))
                        record_corrupt = True
                    else:
                        self.__data += record_data
            elif record_valid:
                # Extra verification of data
                if self.__data[-RECORD_LEN:] != record_data:
                    debug_print("ERROR: Record {:2} primary and secondary "
                            "records don't match".format(self.__rec_idx + 1))
                    record_corrupt = True

            if record_corrupt:
                self.__data_corrupt = True
            else:
                debug_print("Record {:2} sucessfully received".format(
                                self.__rec_idx + 1))

            self.__rec_primary = True
            self.__rec_processed = False
            self.__rec_idx += 1

        self.__buf = ''
        self.__buf_error_mask = ''

        if self.__rec_idx == self.__rec_cnt:
            self.data_complete()
            self.__clear_state()

            return DataProcIface.NOTIFY_DONE

        return DataProcIface.REQUEST_RESYNC

    def __verify_record(self):
        if len(self.__buf) != RECORD_LEN + CHKSUM_LEN:
            print("ASSERT: record buffer incorrect length")
            return False

        chksum = 0
        for x in self.__buf[0:-1]:
            chksum = (chksum + ord(x)) & 0xff

        if chksum != ord(self.__buf[-1]):
            return False

        return True

    def __recover_record(self):
        if not self.__rec_primary_buf:
            return False

        if len(self.__buf) != len(self.__rec_primary_buf):
            return False

        reconstructed_buf = ''
        for i in xrange(0, len(self.__buf)):
            # Check if there are no overlapping bit errors
            byte1_mask = ord(self.__rec_primary_error_mask[i])
            byte2_mask = ord(self.__buf_error_mask[i])
            if (byte1_mask & byte2_mask) != 0:
                return False

            # NOTE: This assums bit errors are set to 0 by lower level decoder
            reconstructed_buf += chr(ord(self.__buf[i]) |
                                     ord(self.__rec_primary_buf[i]))

        self.__buf = reconstructed_buf

        if self.__verify_record():
            return True

        return False

    def data_complete(self):
        if self.__data_corrupt:
            debug_print("ERROR: data received but corrupt")
            debug_print("----------------------------------")
            return

        filename = "{}{:03}.{}".format(
                self.__file_prefix, self.__file_idx,
                self.__file_extension)

        with open(filename, "wb") as outf:
            outf.write(bytes(self.__data, "latin-1"))

        debug_print("Written data to file: " + filename)
        debug_print("----------------------------------")

        self.__file_idx += 1

    def resync_failed_cb(self):
        if not self.__read_header:
            if self._process_record() == DataProcIface.REQUEST_RESYNC:
                return True

        return False

    def process_eof(self):
        if not self.__read_header:
            if self.__rec_idx + 1 == self.__rec_cnt and self.__rec_processed:
                self.data_complete()
            else:
                debug_print("ERROR: EOF but not all records received")

        self.__clear_state()


###############################################################################
# Process edges to bits
###

class BitProcIface(object):
    def process_sample(self, frame_idx, level):
        """Called for every sample. 'level' is the detected bit level."""
        pass

    def process_edge(self, edge_idx, peak_idx, new_level):
        """Called for every change of the bit level to a new level. peak_idx is
        the index of the first sample with the highest/lowest value within the
        level."""
        pass

    def process_eof(self, frame_idx):
        """Called when processing reached the end of file"""
        pass


class BitProc(BitProcIface):
    """ Processes signal edges into bits """

    def __init__(self, data_proc):
        self.__clear_state()
        self.__data_proc = data_proc

    def __clear_state(self):
        self.__last_edge_idx = 0

        self.__training = True
        self.__training_matches = []
        self.__training_start = 0
        self.__edge_cnt = 0  # nr. edges since training start

        self.__resync = False

        self.__symbol_len = 0

        self.__edges_within_symbol = 0

        self.__byte = 0
        self.__bit_error_mask = 0
        self.__bit_cnt = 0

    def _start_resync(self, frame_idx, max_symbols):
        # resync_max_symbol: Add 8 to allow some fluctuation in the
        #                    symbol length
        self.__resync = True
        self.__resync_start_idx = frame_idx
        self.__resync_max_symbol = max_symbols + END_OF_SYNC_SYMBOLS + 8
        self.__byte = 0
        self.__edges_within_symbol = 0

    def process_edge(self, edge_idx, peak_idx, new_level):
        if CONFIG['use_peak']:
            frame_idx = peak_idx
            # FIXME: TEMPORARY HACK FOR LAST BIT... (8 is just a big number...)
            if edge_idx > peak_idx + self.__symbol_len * 8:
                if not self.__data_proc._DataProc__read_header:
                    debug_print("PEAK_TO_EDGE HACK!!!")
                frame_idx = edge_idx
        else:
            frame_idx = frame_idx

        level_len = frame_idx - self.__last_edge_idx
        self.__last_edge_idx = frame_idx

        if self.__training:
            self._process_symbol_training(frame_idx, level_len)
        elif self.__resync:
            self._process_symbol_resync(frame_idx, level_len)
        else:
            self._process_symbol_active(frame_idx, level_len)

    def process_eof(self, frame_idx):
        self.__data_proc.process_eof()

    def _process_symbol_training(self, frame_idx, level_len):
        # Check if the time between edges is constant
        if (abs(level_len - self.__symbol_len) <
                self.__symbol_len * CONFIG['max_bit_diff']):
            self.__training_matches.append(frame_idx)
        else:
            self.__symbol_len = level_len
            self.__training_start = frame_idx
            self.__training_matches = []

        if (len(self.__training_matches) == CONFIG['training_threshold'] and
                self.__symbol_len > CONFIG['min_bit_len']):
            # Compensate symbol len and match start time for better accuracy
            self.__symbol_len = (
                    float(self.__training_matches[-1] -
                        self.__training_start) /
                    len(self.__training_matches))

            if CONFIG['continues_resync']:
                self.__training_start = frame_idx
                self.__edge_cnt = 0

            self.__training_matches = []

            self.__training = False
            self.__edges_within_symbol = 0

            self._start_resync(
                frame_idx,
                MAX_INITIAL_SYNC_SYMBOLS - CONFIG['training_threshold'])

            debug_print("Training Complete, symbol len. = {}".format(
                        self.__symbol_len))

    def _process_symbol_resync(self, frame_idx, level_len):
        # TODO: add possibility to skip record if sync is corrupt

        # Reset state if resync fails
        if (self.__resync_start_idx + self.__resync_max_symbol *
                self.__symbol_len < frame_idx):
            debug_print("   Failed to resync before deadline "
                        "({} > {} + {})".format(
                            frame_idx, self.__resync_start_idx,
                            self.__resync_max_symbol))
            if self.__data_proc.resync_failed_cb() == True:
                self.__resync_start_idx += int(
                    (MAX_RECORD_SYNC_SYMBOLS + END_OF_SYNC_SYMBOLS + (RECORD_LEN + CHKSUM_LEN) * 8) *
                        self.__symbol_len)
                # Add some extra just to be sure, It doesn't hurt if we
                # start half way the 8 resync bytes
                # TODO: is this needed?
                self.__resync_start_idx += int(8 * self.__symbol_len)

                if self.__resync_start_idx < frame_idx:
                    self._process_symbol_resync(frame_idx, level_len)
            else:
                self.__clear_state()
            return

        expected_idx = int(round(
            self.__training_start +
            (self.__edge_cnt + 1) * self.__symbol_len))

        if (abs(frame_idx - expected_idx) <
                self.__symbol_len * CONFIG['max_bit_diff']):
            # At expected symbol boundery

            # Assuming that an even amount of edges within a symbol is just a
            # temporary drop in signal
            if self.__edges_within_symbol % 2 == 1:
                bit = 1
            else:
                bit = 0

            if DEBUG_RESYNC_BITS:
                debug_print("RESYNC {} {}".format(
                            bit, self.__edges_within_symbol))

            self.__byte = ((self.__byte << 1) | bit) & 0xff

            if self.__resync_start_idx > frame_idx:
                # Prevent triggering within a record to be skipped
                # NOTE: The whole resync logic is still run to make sure
                #       the continues resync works.
                pass
            elif self.__byte == 0xff:
                self.__resync = False

            if CONFIG['continues_resync']:
                self.__training_start = frame_idx
                self.__edge_cnt = 0
            else:
                self.__edge_cnt += 1

            self.__edges_within_symbol = 0
        elif frame_idx < expected_idx:
            # Edge within symbol
            self.__edges_within_symbol += 1
        else:
            # Missed symbols

            # Assume missed bits are 0
            self.__byte = 0

            # TODO: consider using remainder to see if current edge is within
            # symbol?
            self.__edges_within_symbol = 0

            missed_symbol_cnt = int(round(
                (level_len + (self.__symbol_len * CONFIG['max_bit_diff'])) /
                self.__symbol_len))

            if CONFIG['continues_resync']:
                self.__training_start = frame_idx
                self.__edge_cnt = 0
            else:
                self.__edge_cnt += missed_symbol_cnt

            if DEBUG_RESYNC_BITS:
                debug_print("RESYNC ! {} {} {}x".format(
                            abs(frame_idx - expected_idx),
                            level_len, missed_symbol_cnt))

    def _process_symbol_active(self, frame_idx, level_len):
        expected_idx = int(round(self.__training_start +
                        (self.__edge_cnt + 1) * self.__symbol_len))

        recurse = False
        bit = None
        bit_error = 0
        if (abs(frame_idx - expected_idx) <
                self.__symbol_len * CONFIG['max_bit_diff']):
            # At expected symbol boundery

            # Assuming that an even amount of edges within a symbol is just a
            # temporary drop in signal
            if self.__edges_within_symbol % 2 == 1:
                bit = 1
            else:
                bit = 0

            if DEBUG_BITS:
                debug_print("{} {}".format(bit, self.__edges_within_symbol))

            self.__edges_within_symbol = 0
        elif frame_idx < expected_idx:
            # Edge within symbol
            self.__edges_within_symbol += 1
            return
        else:
            # Missed symbols

            # Reconstruct missed symbol to keep bit sync
            if DEBUG_BITS:
                debug_print("!")

            # NOTE: edges_within_symbol can't be used here. Because when using
            # peak detection and the signal has died out(ie. last bit) then
            # there will always be a peak within the symbol due to any ofshoot
            # of the previous peak.
            # UPDATE: hack in process_edge() should fix this for now...
            if self.__edges_within_symbol % 2 == 1:
                bit = 1
            else:
                bit = 0
            bit_error = 1
            self.__edges_within_symbol = 0
            recurse = True

        self.__edge_cnt += 1

        self.__byte = ((self.__byte << 1) | bit) & 0xff
        self.__bit_error_mask = (
            ((self.__bit_error_mask << 1) | bit_error) & 0xff)
        self.__bit_cnt += 1

        if self.__bit_cnt == 8:
            ret = self.__data_proc.process_byte(self.__byte,
                                                self.__bit_error_mask)

            if ret is DataProcIface.REQUEST_RESYNC:
                self._start_resync(frame_idx, MAX_RECORD_SYNC_SYMBOLS)
            elif ret is DataProcIface.NOTIFY_DONE:
                self.__clear_state()
                # Don't try to reconstruct any more bits since data is all
                # received and any new data blob starts with a training
                # sequence
                recurse = False

            self.__bit_cnt = 0
            self.__byte = 0

        if CONFIG['continues_resync']:
            if recurse:
                self.__training_start = expected_idx
            else:
                self.__training_start = frame_idx
            self.__edge_cnt = 0

        if recurse:
            self._process_symbol_active(
                frame_idx,
                int(round(level_len - self.__symbol_len)))


###############################################################################
# Process signal to level/edges
###

class SignalProcIface(object):
    """ Interface for classes that handle raw samples """
    def process_sample(self, sample):
        pass

    def process_eof(self):
        pass


class SignalProc(SignalProcIface):
    """ Process Signal into edges and levels """

    def __init__(self, bit_proc, debug_wave=None):
        self.__frame_idx = 0

        self.__range_max = -0x10000
        self.__range_min = 0x10000
        self.__idle = True
        self.__level = 0
        self.__peak = 0
        self.__peak_idx = 0

        self.__bit_proc = bit_proc

        self.__debug_wave = None
        if debug_wave:
            self._open_debug_wave(debug_wave)

    def _open_debug_wave(self, filename):
        self.__debug_wave = wave.open(filename, 'wb')
        self.__debug_wave.setnchannels(6)
        self.__debug_wave.setsampwidth(2)
        self.__debug_wave.setframerate(44100)

    def process_sample(self, sample):
        global debug_frame_idx

        # TODO: level/volume/clipping detection/warning

        # Set dynamic threshold calculation
        self.__range_max = self.__range_max * CONFIG['range_decay']
        self.__range_min = self.__range_min * CONFIG['range_decay']
        if sample > self.__range_max:
            self.__range_max = sample
        if sample < self.__range_min:
            self.__range_min = sample
        dyn_range = self.__range_max - self.__range_min
        threshold = self.__range_min + dyn_range / 2

        # Peak detection
        if ((self.__level == 1 and sample > self.__peak) or
                (self.__level == 0 and sample < self.__peak)):
            self.__peak = sample
            self.__peak_idx = self.__frame_idx

        # Determine Logic Level and Edge detection
        edge = False
        if (self.__level == 0 and
                sample > threshold + (dyn_range/2) * CONFIG['hysteresis']):
            self.__level = 1
            edge = True
        elif (self.__level == 1 and
                sample < threshold - (dyn_range/2) * CONFIG['hysteresis']):
            self.__level = 0
            edge = True

        # Bit processor callbacks
        self.__bit_proc.process_sample(self.__frame_idx, self.__level)
        if edge:
            self.__bit_proc.process_edge(self.__frame_idx, self.__peak_idx, self.__level)

        # DEBUG: write debug wave
        if self.__debug_wave:
            self.__debug_wave.writeframes(
                struct.pack("<hhhhhh",
                            sample,
                            0x7000 if self.__level else 0,
                            self.__range_max,
                            self.__range_min,
                            threshold,
                            self.__peak))

        self.__frame_idx += 1
        debug_frame_idx += 1

    def process_eof(self):
        self.__bit_proc.process_eof(self.__frame_idx)


###############################################################################
# Main
###

parser = argparse.ArgumentParser(
    description='Decode TI-99/4a cassette tapes')
parser.add_argument(
    'input_file', nargs='?',
    help='path to wave file to decode. If not specified default capture '
         'source of soundcard will be used')
parser.add_argument(
    '--debug-wave',
    dest="debug_wave", default=None,
    metavar='FILE',
    help='Dump internal wave forms to file for debugging')
parser.add_argument(
    '--profile',
    dest="profile", default=DEFAULT_PROFILE,
    choices=list(profiles.keys()).append('?'),
    metavar='P',
    help="Use given decoder configuration profile. Use '?' to get "
         "a list of available profiles. Default: " +
         DEFAULT_PROFILE)
parser.add_argument(
    '--file-prefix',
    dest='file_prefix', default='tape_',
    metavar='PREFIX',
    help="Output filename prefix. default: 'tape_'")
parser.add_argument(
    '--channel',
    dest='input_channel', type=int, default=0,
    metavar='CHAN',
    help="Input audio channel to decode, default: 0")
parser.add_argument(
    '--version',
    action='version',
    version='%(prog)s {}.{}'.format(VERSION_MAJOR, VERSION_MINOR))

args = parser.parse_args()

if args.profile == '?':
    print("Available profiles:")
    for k in profiles.keys():
        print("  {} - {}{}".format(
            k, profiles[k]['description'],
            " (Default)" if k == DEFAULT_PROFILE else ""))
    exit(0)

CONFIG = profiles[args.profile]

data_proc = DataProc(file_prefix=args.file_prefix)
bit_proc = BitProc(data_proc)
sig_proc = SignalProc(bit_proc, debug_wave=args.debug_wave)

if args.input_file is None:
    p = pyaudio.PyAudio()

    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=44100,
                    input=True,
                    output=True)

    stream.start_stream()

    try:
        while True:
            data = stream.read(1)
            sample = struct.unpack("<h", data)[0]

            sig_proc.process_sample(sample)

            stream.write(data)
    except:
        traceback.print_exc(file=sys.stdout)

    stream.stop_stream()
    stream.close()

    p.terminate()
else:
    wf = wave.open(args.input_file, 'rb')
    channel = args.input_channel

    if channel >= wf.getnchannels():
        raise IndexError("Input channel number out-of-range")

    data = wf.readframes(100)
    while len(data) > 0:
        sample_len = wf.getnchannels() * wf.getsampwidth()

        for i in range(0, len(data), sample_len):
            if wf.getsampwidth() == 2:
                sample = struct.unpack_from("<h", data, i + channel * 2)[0]
            elif wf.getsampwidth() == 1:
                sample = ord(data[i + channel])
            else:
                print("Wave file uses unsupported sample width")
                exit(-1)

            sig_proc.process_sample(sample)

        data = wf.readframes(100)

    wf.close()

sig_proc.process_eof()
