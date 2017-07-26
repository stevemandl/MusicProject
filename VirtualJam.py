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
from mingus.core import chords, meter as mtr
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
        tonic = chords.I(keys.get_notes(key)[0])
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
        return self._chords[int(beat)]
     
    def setTones(self, tones):
        """ replaces the tones, recalculates the internal track and beats """
        self._tones = tones
        #update the track whenever the tones are modified:
        self._track = makeTrack(tones, self) # a SongPart suffices as a Context
        self.beats = max([self.beats]+[t.getEndTime() for t in tones])
        
    def setBarProgresion(self, progression):
        bpmx = getBPMX(self.meter)
        #self._chords = (bpmx * len(progression))*[None]
        b = 0 
        for p in progression:
            c = eval('chords.%s' % p)(self.key)
            self.setChords(c, range(b,b+bpmx))
            b += bpmx
        self.beats = max([self.beats, b])
        
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
        assert(mtr.is_valid(meter))
        self.meter = meter
        self._bpmx = getBPMX(meter)
        self.current_section = None
        self.current_beat = 0.0
        self.parts = {} # part_ref: instance of SongPart
        self.clearArrangement()
                
    def addPart(self, part_ref, part):
        self.parts[part_ref] = part
    
    def clearArrangement(self):
        self.arrangement = [] # array of sections (part_ref, part_type, beat_start)
        self.bars = []
        self.total_beats=0.0
        self._track = Track()
        
    def _currentBar(self):
        #TODO: fix this if we ever want to change meter mid-song (no money)
        return int(self.current_beat / self._bpmx)
    
    def getCurrentBar(self):
        return self._track.bars[self._currentBar()]
    
    def getBeatInBar(self):
        return self.current_beat - self._currentBar() * self._bpmx
    
    def getCurrentSection(self):
        cb = self._currentBar()
        return self.arrangement[self._currentBar()]
    
    def getCurrentPart(self):
        return self.parts[self.getCurrentSection()[0]]
    
    def getCurrentChord(self):
        return self.getCurrentPart().chordAt(self.current_beat - self.getCurrentSection()[2])
    
    def getCurrentKey(self):
        return self.parts[self.getCurrentSection()[0]].key
    
    def getCurrentMeter(self):
        return self.parts[self.getCurrentSection()[0]].meter
    
    def appendArrangement(self, part_ref, part_type):
        assert(part_type in SongContext._part_types and part_ref in self.parts)
        beat_start = self.total_beats
        self.total_beats += self.parts[part_ref].beats
        for bar in self.parts[part_ref]._track.bars:
            self._track.add_bar(bar)
            self.arrangement.append((part_ref, part_type, beat_start))
        
    
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
        """ return a track from the given start to end
        this just plays the context's melody verbatim"""
        self._cx.current_beat = startBeat
        t = Track()
        context.current_beat = startBeat
        cBar = context.getCurrentBar()
        bar = Bar(context.getCurrentKey(), context.getCurrentMeter())
        # place a rest at the start of the first bar in case we don't start on a bar boundary
        if context.getBeatInBar() > 0:
            bar.place_rest(1.0 / context.getBeatInBar())
            
        #add notes
        for beat in range(startBeat, endBeat):
            context.current_beat = beat
            cxBar = context.getCurrentBar()
            #append the previous bar if we are on to a new one
            if cxBar != cBar:
                cBar = cxBar
                t.add_bar(bar)
                bar = Bar(context.getCurrentKey(), context.getCurrentMeter())
            for s,d,n in filter(lambda x: x[0] <= context.getBeatInBar() 
                        and x[0] >= bar.current_beat, cxBar):
                bar.place_notes(n, d)
        if not bar.is_full():
           bar.place_rest(1.0 / (bar.length - bar.current_beat))
        t.add_bar(bar)    
        return t

#
# BluesPlayer class
#

class BluesPlayer(Player):
    """ picks blues licks to play that fit the context """
    def play(self, startBeat, endBeat):
        #TODO: implement this
        return super(BluesPlayer, self).play(startBeat, endBeat)
    
#
#
#

class ElementaryBassPlayer(Player):
    """plays quarter notes at the root of the chord"""
    def play(self, startBeat, endBeat):
        self._cx.current_beat = startBeat
        t = Track()
        context.current_beat = startBeat
        cBar = context.getCurrentBar()
        bar = Bar(context.getCurrentKey(), context.getCurrentMeter())
        # place a rest at the start of the first bar in case we don't start on a bar boundary
        if context.getBeatInBar() > 0:
            bar.place_rest(1.0 / context.getBeatInBar())
            
        #add notes
        for beat in range(startBeat, endBeat):
            context.current_beat = beat
            n = Note(context.getCurrentChord()[0])
            n.change_octave(-2)
            bar.place_notes(n, bar.meter[1])
            # next bar?
            if bar.is_full():
                t.add_bar(bar)
                bar = Bar(context.getCurrentKey(), context.getCurrentMeter())
        if not bar.is_full():
           bar.place_rest(1.0 / (bar.length - bar.current_beat))
        t.add_bar(bar)    
        return t
             
    
#
# ReharmonizationPlayer class
#
#TODO: should this inherit from player? Will it play?
class ReharmonizationPlayer(Player):
    """ this player will reharmonize sections of a SongContext"""
    def reharmonize(self, sectionRange):
        """For the sections in sectionRange (e.g. [4,5,7]),
           create alternate parts with substitute chords and 
           replace the references in the arrangement to the alternates """
        #TODO: implement this
        pass

#some helpful functions...

# quantize rounds the time to the nearest quanta
def quantize(t):
    return round(t / qSz ) * qSz

def getBPMX(meter):
    """ return the number of beats per measure given a meter""" 
    #TODO: handle compond meters
    return meter[0]

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
    bpmx = getBPMX(cx.meter) # beats per measure 
    tone_t = (0, 0.0)
    sBar = eBar = None
    # process tones
    for tone in s_tones:
        sBar = int(tone.beatTime / bpmx) #starting bar for this tone
        eBar = int(tone.getEndTime() / bpmx) #ending bar for this tone
        for bar in range(sBar, eBar+1):
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
        blueTones = [Tone(*x) for x in [(60,0,0.25),(64,0.25,0.25),(67,0.5,0.25),(72,0.75,0.25),
                                        (75,1,0.25),(74,1.25,0.25),(72,1.5,0.25),(69,1.75,0.25),
                                        (60,2,0.25),(64,2.25,0.25),(67,2.5,0.25),(72,2.75,0.25),
                                        (70,3,0.25),(67,3.25,0.25),(64,3.5,0.25),(60,3.75,0.25),
                                        (75,4,0.25),(74,4.25,0.25),(72,4.5,0.25),(69,4.75,0.25),
                                        (75,5,0.25),(74,5.25,0.25),(72,5.5,0.25),(69,5.75,0.25),
                                        (60,6,0.25),(64,6.25,0.25),(67,6.5,0.25),(72,6.75,0.25),
                                        (60,7,0.25),(64,7.25,0.25),(67,7.5,0.25),(72,7.75,0.25),
                                        (62,8,0.25),(67,8.25,0.25),(71,8.5,0.25),(74,8.75,0.25),
                                        (75,9,0.25),(74,9.25,0.25),(72,9.5,0.25),(69,9.75,0.25),
                                        (60,10,0.25),(64,10.25,0.25),(67,10.5,0.25),(72,10.75,0.25),
                                        (62,11,0.25),(67,11.25,0.25),(71,11.5,0.25),(74,11.75,0.25)
                                        ]]
        k = context.key
        A = SongPart(48, key=k, meter=context.meter)
        progression = ['I','IV7','I','I7','IV7','IV7','I','I','V7','IV7','I7','V7']
        A.setBarProgresion(progression)
        A.setTones(blueTones)
        print " A track", A._track
        print " A beats", A.beats
        context.addPart('A', A)
        context.appendArrangement('A', 'verse')
        bassPlayer = ElementaryBassPlayer(context)
        print "total beats: " ,int(context.total_beats)
        trk = bassPlayer.play(0, int(context.total_beats))
        fluidsynth.play_Track( trk )
        
    stream.stop_stream()
    stream.close()
    p.terminate()