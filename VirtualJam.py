#! /usr/bin/env python
""" VirtualJam is an interactive music generation tool
thanks to aubio and mingus, and the examples posted on their sites
"""

import pyaudio
import sys
import numpy as np
import aubio
import time
import math
from mingus.midi import fluidsynth
from mingus.containers import Track, Bar, Note
import mingus.core.keys as keys
from mingus.core import chords
import argparse

_debug = 0

#some classes...

#
# Tone class
#

class Tone(object):
    """ has a midi note value (pitch), beat time, and duration """
    def __init__(self, midiNote, beatTime, duration):
        self.midiNote = midiNote
        self.beatTime = beatTime
        self.duration = duration
    
    def setEndTime(self, endTime):
        self.duration = endTime - self.beatTime
    
    def getEndTime(self):
        return self.beatTime + self.duration
    
    def asNote(self):
        n = None
        if self.midiNote > 0:
            n = Note()
            n.from_int(int(self.midiNote))
        return n
    def __repr__(self):
        return "Tone: %s pitch:%d beat:%f len: %f" % (self.asNote(), self.midiNote, self.beatTime, self.duration)

#        
# SongPart class
#

class SongPart(object):
    """encapsulates a part of a song """
    def __init__(self, beats, key='C', meter=(4,4)):
        assert keys.is_valid_key(key)
        self.key = key
        self.meter = meter
        self.beats = beats #integer number of beats in this part
        tonic = chords.determine([keys.get_notes(key)[n] for n in [0,2,4]])[0]
        self._chords = beats*[tonic]
        self._tones = []
        
    # setChords() 
    def setChords(self, chord, beatRange):
        """fills in a range of beats with the given chord """
        for b in beatRange:
            self._chords[b] = chord
            
    # chordAt() 
    def chordAt(self, beat):
        """returns the chord at the beat in question """
        return _chords[beat]
     
    def setTones(self, tones):
        """ replaces the tones, recalculates the internal track and beats """
        self._tones = tones
        #update the track whenever the tones are modified:
        self._track = makeTrack(tones, self) # a SongPart suffices as a Context
        self.beats = max(tones, key=lambda e: e.getEndTime())
        
    def setBarProgresion(self, progression):
        #TODO: fix this for compond meter
        bpmx = self.meter[0]
        b = 0 
        for p in progression:
            c = eval('chords.%s' % p)(self.key)
            setChords(c, (b,b+bpmx))
            b += bpmx
        
    
    def noteAt(self, beat):
        """ returns the base melodic note at the beat in question """ 
        # TODO: this needs to be implemented 
        pass

#
# SongContext class
#  
 
class SongContext(object):
    """ this captures the global key and meter, the arrangement, 
    and the notion of a current state within the song
    """ 
    _part_types=['intro', 'verse', 'chorus', 'bridge', 'coda']
    def __init__(self, key='C', meter=(4,4)):
        """Set up a song context"""
        self.key = key
        self.meter = meter
        self.current_section = None
        self.current_beat = 0.0
        self.parts = {} # part_ref: instance of SongPart
        self.clearArrangement()
                
    def addPart(self, part_ref, part):
        self.parts[part_ref] = part
    
    def clearArrangement(self):
        self.arrangement = [] # array of sections (part_ref, part_type)
        self.bars = []
        self.total_beats=0.0
        self._track = Track()
        
    def _currentBar(self):
        return int(self.current_beat / self.meter[1])
    
    def getCurrentBar(self):
        return self._track.bars[_currentBar()]
    
    def getCurrentSection(self):
        return self.arrangement[_currentBar()]
    
    def appendArrangement(self, part_ref, part_type):
        assert(part_type in _part_types and part_ref in self.parts)
        self.total_beats += (len(self.parts[part_ref]) * self.meter[1])
        for bar in self.parts[part_ref]._track.bars:
            self._track.add_bar(bar)
            self.arrangement.append((part_ref, part_type))
        
    
    def nextNote(self):
        """ moves the current_beat to the next note in the song 
        traverses to the next part if necessary. Returns None if there is
        nothing left to play"""
        #TODO: if there is nothing left in the current section, move to the next section 
        #TODO: find the next note in the current section, set the current_beat and return the note
        return None

#
# Player Class
#

class Player():
    """ This is the base class for a music playing algorithm """
    def __init__(self, context):
        self._cx = context
        
    def play(self, startBeat, endBeat):
        """ return a track from the given start to end"""
        self._cx.current_beat = startBeat
        t = Track()
        #TODO: add notes
        return t
    
    
    
#some helpful functions...

# quantize rounds the time to the nearest quanta
def quantize(t):
    return round(t / qSz ) * qSz

# tick_metronome plays a short sound
def tick_metronome():
    fluidsynth.play_Note(90,0,100) and fluidsynth.stop_Note(90,0)

# makeTrack
# takes a list of Tones and a Context, and returns a mingus Track 
def makeTrack(tones, cx):
    t = Track()
    s_tones = sorted(tones, key=lambda x: x.beatTime)
    num_bars = 1 + math.floor(s_tones[-1].getEndTime() / cx.meter[0])
    for _ in range(int(num_bars)):
        t.add_bar(Bar(cx.key, cx.meter))
    bpmx = cx.meter[0] # beats per measure 
    tone_t = (0, 0.0)
    sBar = eBar = None
    #TODO: process note, beat, noteLen
    for tone in s_tones:
        print "tone: %s" % tone
        sBar = int(tone.beatTime / bpmx) #starting bar for this tone
        eBar = int(tone.getEndTime() / bpmx) #ending bar for this tone
        print "bars: %d %d" % (sBar, eBar )
        for bar in range(sBar, eBar+1):
            print "bar: %d" % bar
            mNote = tone.asNote()
            if bar < eBar:
                if mNote: mNote.dynamics['tie']= True #tie the note over to the next bar
                mLen = t[bar].space_left()
            else:
                mLen = tone.getEndTime() / bpmx - bar - t[bar].current_beat
            if mLen > 0: t[bar].place_notes(mNote, 1.0/mLen)
    return t

# getToneStream
# listens to the micropohone for notes being played
# yields a stream of Tones as they are recognized
def getToneStream(duration = -1, play_metronome=True):
    print("*** starting recording")
    lastBeat = -1
    lastConf = MIN_CONF
    walog = 0.1
    tone = None
    beatTime = -1
    currentBeat = 0
    starttime = time.time()
    while duration < 0 or currentBeat < duration: 
        audiobuffer = stream.read(buffer_size)
        now = time.time()
        currentBeat = quantize((now - starttime) / beatSz)
        signal = np.fromstring(audiobuffer, dtype=np.float32)
        sMax = np.amax(signal)
        attack = (sMax / walog) > 2
        pitch = round(pitch_o(signal)[0]) # round to nearest semitone
        confidence = pitch_o.get_confidence()
        confident = confidence > MIN_CONF
        if (math.trunc(currentBeat) != lastBeat) and play_metronome:
            tick_metronome()
            lastBeat = math.trunc(currentBeat)
        if attack and confident: #sudden increase in volume
            if tone and tone.beatTime == currentBeat: # ignore grace note
                tone.midiNote = pitch 
            else:
                if tone:
                    tone.setEndTime(currentBeat)
                    yield(tone)
                tone = Tone(pitch, currentBeat, 0) # duration is not known yet
                lastConf = confidence
        elif tone and not confident:
            tone.setEndTime(currentBeat)
            yield(tone)
            tone = None
        elif (confidence > lastConf) and tone and not attack:
            tone.midiNote = pitch
            lastConf = confidence
        walog = (sMax + walog) /2.0 #weighted avg peak amplitude
    if tone:
        tone.setEndTime(duration)
        yield(tone)

# __main__
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Listen and respond to music.')
    parser.add_argument('--echo','-e', action='store_true', default=False,
                        help='listen for a while, then playback the notes that were heard. (default: %(default)s)')
    parser.add_argument('--key','-k', type=str, default='C',
                        help='Starting key signature. (default: %(default)s)')
    parser.add_argument('--size','-s', metavar='LOOPSIZE', type=int, default=16,
                        help='Number of beats to sample before ending loop. (default: %(default)s)')
    parser.add_argument('--bpm','-b', type=float, default=90.,
                        help='Beats per minute. (default: %(default)s)')
    parser.add_argument('--qpm','-q', type=float, default=360.,
                        help='Quanta per minute; determines how finely to quantize. (default: %(default)s)')
    parser.add_argument('--blues','-z', action='store_true', default=False,
                        help='Play some blues. (default: %(default)s)')
    parser.add_argument('--output', default=None,
                        help='Output file for results. (default: %(default)s)')
    parser.add_argument('--debug', action='store_true')
    options = parser.parse_args()
    if hasattr(options, 'help'):
        sys.exit()
    if options.debug: 
        print "options:%r"%(options)
        _debug = 1

    #init stuff
    # open stream
    buffer_size = 1024
    pyaudio_format = pyaudio.paFloat32
    n_channels = 1
    samplerate = 44100
    bpm = options.bpm
    qpm = options.qpm
    beatSz = 60.0 / bpm
    qSz = bpm/qpm
    MIN_CONF = 0.33 #minimum confidence in pulling a note from a signal
    fluidsynth.init("/usr/share/sounds/sf2/grand-piano-YDP-20160804.sf2", "alsa")
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio_format,
                    channels=n_channels,
                    rate=samplerate,
                    input=True,
                    frames_per_buffer=buffer_size)
    # setup pitch
    tolerance = 0.8
    win_s = 4096 # fft size
    hop_s = buffer_size # hop size
    pitch_o = aubio.pitch("default", win_s, hop_s, samplerate)
    pitch_o.set_unit("midi")
    pitch_o.set_tolerance(tolerance)
    
    track_o = aubio.tempo("specdiff", win_s, hop_s, samplerate)
    loop_size = options.size
    context = SongContext(key=options.key)    

    if options.echo:
        loop=[]
        for n in getNoteStream(loop_size):
            loop.append(n)
        trk = makeTrack(loop, context)
        print "Track:"
        print trk
        fluidsynth.play_Track( trk ) 

    if options.blues:
        k = context.key
        A = SongPart(48, key=k, meter=context.meter)
        progression = ['I','IV','I','I','IV','IV','I','V','IV','I','I','V7']
        A.setBarProgresion(progression)
        context.addPart('A', A)
        context.appendArrangement('A', 'verse')
        p = Player(context)
        trk = p.play(0, context.total_beats)
        fluidsynth.play_Track( trk )
        
    stream.stop_stream()
    stream.close()
    p.terminate()
