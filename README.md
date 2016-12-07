# TI-99/4a home computer cassette tape de-/encoder
Tool for decoding and encoding TI-99/4a cassette tape recordings.

Basic operation:

   ti99_4a_tape_decode.py [input_file]

Where input_file is a 16-bit signed WAV file.

If the tool successfully decodes a program it will create a file named
'tape_XXX.dat' for every program found. The output files contain the raw data
of the program.

To re-encode a program run:

    ti99_4a_tape_encode.py [input_file]

Or use the HTML5 based encoder, ti99_4a_tape_encode.html.

## Recording tape to .WAV
Although ti99_4a_tape_decode.py is able to work from live input it is in
general a better idea to first record the tape to a .wav file. This allows you
to try out different decoder settings without having to play the tape again.
And using a recoding application that gives visual feedback of the recording
levels allows for selecting the optimal input volume.

A good tool for recording audio is Audacity.

When recording try to prevent clipping due to the input volume being to loud.
In general a max. recording level of about -3 db should be okay.

The tape data is in mono, but I found that recording in stereo gives better
results.

Files must be in the 'WAV (Microsoft) signed 16-bit PCM' format. In Audacity
this can be done using the export audio option.

## Debugging conversion failures
All console output of ti99_4a_tape_decode is prepended with a number. This is
the index of the current sample being processed. These indexes can be used for
closer inspection of the wave form at the point of the issue.

For debugging the decoder parameters the '--debug-wave' argument can be used.
This will generate a new .WAV file with the original wave form and the
calculated peak, threshold and bit levels.
