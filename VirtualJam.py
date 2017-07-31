#! /usr/bin/env python
""" VirtualJam is an interactive music generation tool
thanks to aubio and mingus, and the examples posted on their sites
need to install 
https://github.com/anzev/mingus/archive/master.zip

"""
from Beatles import *
from ChordPaths import *
from Sieve import Sieve
import logging
import argparse
import aubio
import math
from mingus.containers import Track, Bar, Note, Composition, note
from mingus.core import chords, meter as mtr
from mingus.midi import fluidsynth
from mingus.midi.midi_file_out import write_Composition
import sys
import time
import random
import mingus.core.keys as keys
import numpy as np
import pyaudio


_debug = 0
logging.basicConfig()
_log = logging.getLogger('VirtualJam')
_log.setLevel(logging.INFO)

#some classes...

#
# Tone class
#

class Tone(object):
    """ has a midi note value (pitch), beat time, and duration """
    def __init__(self, note, beatTime, duration):
        if isinstance (note, (int, float, long)):
            self.midiNote = note
        elif type(note) == str:
            self.midiNote = int(Note(note))
        elif hasattr(note, 'name'):
            self.midiNote = int(note)
        else:
            raise Exception("Can't handle note object: '%s'" % note)
        
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
            n.dynamics = {}
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
        v_notes = filter(lambda x: x.beatTime <= beat and x.getEndTime() > beat, self._tones)
        if v_notes:
            return v_notes[0].as_note()
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
        """_currentBar() for internal use, returns the index of the current bar"""
        #TODO: fix this if we ever want to change meter mid-song (no money)
        bbb = int(self.current_beat / self._bpmx)
        _log.debug( "_currentbar: %d beat %f" , bbb, self.current_beat) 
        return bbb
     
    def getCurrentBar(self):
        """# getCurrentBar() returns the current Bar"""
        return self._track.bars[self._currentBar()]
    
    def getBeatInBar(self):
        """returns the position in the current bar that the current_beat is in"""
        return self.current_beat - self._currentBar() * self._bpmx
    
    def getCurrentSection(self):
        """returns the section (ref, type, start) the current_beat is in"""
        sss = self.arrangement[self._currentBar()]
        _log.debug( 'currentSection: %s' , sss[0])
        return sss
    
    def getCurrentPart(self):
        """returns the SongPart referenced in the current_beat"""
        return self.parts[self.getCurrentSection()[0]]
    
    def getCurrentChord(self):
        """returns the Chord from SongPart at the current_beat"""
        return self.getCurrentPart().chordAt(self.current_beat - self.getCurrentSection()[2])
    
    def getCurrentNote(self):
        """returns the Note from SongPart at the current_beat"""
        return self.getCurrentPart().noteAt(self.current_beat - self.getCurrentSection()[2])
    
    def getCurrentKey(self):
        """returns the key of the songPart at the current_beat """
        return self.getCurrentPart().key
    
    def getCurrentMeter(self):
        """returns the meter of the songPart at the current_beat """
        return self.getCurrentPart().meter
    
    def appendArrangement(self, part_ref, part_type):
        """appends a reference to the part_ref of type part_type to the arrangement """
        assert(part_type in SongContext._part_types and part_ref in self.parts)
        beat_start = self.total_beats
        self.total_beats += self.parts[part_ref].beats
        for bar in self.parts[part_ref]._track.bars:
            if bar: # skip empty bars
                self._track.add_bar(bar)
                self.arrangement.append((part_ref, part_type, beat_start))
    
    def nextNote(self):
        """ moves the current_beat to the next note in the song 
        traverses to the next part if necessary. Returns None if there is
        nothing to play"""
        # return the current note, incrementing the current_beat to the start of the next note
        while self.current_beat < self.total_beats:
            cBar = self.getCurrentBar()
            cNote = self.getCurrentNote()
            cBiB = self.getBeatInBar()
            nextNotes = [n[0] for n in cBar if n[0] > cBiB]
            if nextNotes:
                diff = min(nextNotes) - cBiB
                self.current_beat += diff
                return cNote
            # if there are no more notes in the bar, move to the next bar
            diff = cBar.length - cBiB
            if diff <= 0: 
                break
            self.current_beat += diff
        # return None if we are at the end.
        return None

#
# Player Class
#

class Player():
    """ This is the base class for a music playing algorithm """
    def __init__(self, context):
        self._cx = context
        
    def _bar(self):
        """a new bar for the players context"""
        return Bar(self._cx.getCurrentKey(), self._cx.getCurrentMeter())
    
    def _cBar(self):
        """the context's current bar"""
        return self._cx.getCurrentBar()
    
    def _bib(self):
        """the context's beat in bar"""
        return self._cx.getBeatInBar()
        
    def play(self, startBeat, endBeat):
        """ return a track from the given start to end
        this just plays the context's melody verbatim"""
        self._cx.current_beat = startBeat
        t = Track()
        cBar = self._cBar()
        bar = self._bar()
        # place a rest at the start of the first bar in case we don't start on a bar boundary
        if self._bib() > 0:
            bar.place_rest(1.0 / self._bib())
            
        #add notes
        for beat in range(startBeat, endBeat):
            self._cx.current_beat = beat
            cxBar = self._cBar()
            #append the previous bar if we are on to a new one
            if cxBar != cBar:
                cBar = cxBar
                t.add_bar(bar)
                bar = self._bar()
            for s,d,n in filter(lambda x: x[0] <= self._bib() 
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
# ElementaryBassPlayer class
#

class ElementaryBassPlayer(Player):
    """plays quarter notes at the root of the chord"""
    def play(self, startBeat, endBeat):
        self._cx.current_beat = startBeat
        t = Track()
        bar = self._bar()
        # place a rest at the start of the first bar in case we don't start on a bar boundary
        if self._bib() > 0:
            bar.place_rest(1.0 / self._cx.getBeatInBar())
            
        #add notes
        for beat in range(startBeat, endBeat):
            context.current_beat = beat
            n = Note(context.getCurrentChord()[0])
            n.change_octave(-2)
            bar.place_notes(n, bar.meter[1])
            # next bar?
            if bar.is_full():
                t.add_bar(bar)
                bar = self._bar()
        if bar.current_beat > 0.0001:
            if not bar.is_full():
                bar.place_rest(1.0 / (bar.length - bar.current_beat))
            t.add_bar(bar)    
        return t

#
# WalkingBassPlayer class
#

class WalkingBassPlayer(Player):
    def play(self, startBeat, endBeat):
        self._cx.current_beat = startBeat
        t = Track()
        bar = self._bar()
        bass_range = range(16,43) 
        chordSieve = Sieve(bass_range)
        walk_direction = 3
        if coin(): walk_direction = -3
        last_chord = self._cx.getCurrentChord()
        chordSieve.overlay(bass_range, last_chord[:1]) #only roots
        walk_note = chordSieve.attune(Note('D-2'))
        last_note = chordSieve.attune(Note('D-2'))
        last_goal = (startBeat, walk_note)
        nearby_notes = [last_goal]
        
        # add goal Notes at the start of each chord change
        while self._cx.current_beat < endBeat:
            if self._cx.getCurrentChord()[0] != last_chord[0] or self._cx.current_beat == endBeat-1:
                chordSieve.overlay(bass_range, self._cx.getCurrentChord()[:1])
                dt = self._cx.current_beat - last_goal[0]
                new_range = [n for n in bass_range if n >= (int(last_goal[1]) - dt * 5) and n < (int(last_goal[1]) + dt * 5 ) ]
                new_goal = (self._cx.current_beat, chordSieve.attune(random.choice(new_range)))
                _log.debug("WalkingBass goal diff %d", int(new_goal[1]) - int(last_goal[1]) )
                for n in range(dt):
                    if n == 0: #first note when chord changed
                        nearby_notes.append(last_goal) #land on goal note when chord changes
                        walk_note = last_goal[1]
                        continue
                    # constrain wal direction so we don't get out of range or too far from goal
                    if walk_direction >= 0 and (walk_note > 42 or coin(1. / (43 - int(walk_note)))):
                        walk_direction = -2 
                    if walk_direction <= 0 and (walk_note < 17 or coin(1. / (int(walk_note) - 16))):
                        walk_direction = 2 
                    if int(walk_note) - int(new_goal[1]) > (dt-n) * 4: walk_direction = -5
                    if int(new_goal[1]) - int(walk_note) > (dt-n) * 4: walk_direction = 5
                    #overlay a scale  
                    chordSieve.overlay(bass_range, determineScale(last_chord))
                    walk_note = int(walk_note) + walk_direction    
                    walk_note = chordSieve.attune(walk_note, walk_direction > 0)
                    if not n % 2: #even notes sieve with chord
                        chordSieve.overlay(bass_range, last_chord)
                        walk_note = chordSieve.attune(walk_note, walk_direction > 0)
                    #TODO: add rhythm filter e.g. append only if beat_in_bar in rhythm_beats
                    if last_note != walk_note:
                        nearby_notes.append((last_goal[0] + n, walk_note))
                    else:
                        nearby_notes.append((last_goal[0] + n, 0))
                    last_note = walk_note
                last_goal = new_goal
            last_chord = self._cx.getCurrentChord()
            self._cx.current_beat += 1
        
        #add notes
        for beat, note in nearby_notes:
            context.current_beat = beat
            if note: 
                n = Note(note)
            else:
                n = None
            bar.place_notes(n, bar.meter[1])
            # next bar?
            if bar.is_full():
                t.add_bar(bar)
                bar = self._bar()
        if bar.current_beat > 0.0001:
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

#flip a coin
def coin( p = 0.5 ): return random.random() > p

# tick_metronome plays a short sound
def tick_metronome():
    fluidsynth.play_Note(90,0,100) and fluidsynth.stop_Note(90,0)

# makeTrack
# takes a list of Tones and a Context, and returns a mingus Track 
def makeTrack(tones, cx):
    t_track = Track()
    #s_tones = sorted(tones, key=lambda x: x.beatTime)
    last_time = max([t.getEndTime() for t in tones])
    for _ in range(1 + int(last_time / cx.meter[0])):
        t_track.add_bar(Bar(cx.key, cx.meter))
    mpx = 1.0 / getBPMX(cx.meter) # measure portion of a beat as a float 
    sBar = eBar = None
    # process tones
    for tone in tones:
        sBar = int(tone.beatTime * mpx) #starting bar for this tone
        eBar = int(math.ceil(tone.getEndTime() * mpx)) #ending bar for this tone
        for bar in range(sBar, eBar):
            mNote = tone.asNote()
            if bar < (eBar - 1):
                if mNote:
                    mNote.dynamics['tie']= True #tie the note over to the next bar
                mLen = t_track[bar].space_left()
            else:
                mLen = tone.getEndTime() * mpx - bar - t_track[bar].current_beat
            if mLen > 0:
                t_track[bar].place_notes(mNote, 1.0 / mLen)
    return t_track

# getToneStream
# listens to the micropohone for notes being played
# yields a stream of Tones as they are recognized
def getToneStream(duration = -1, play_metronome=True):
    _log.info("*** starting recording")
    lastBeat = -1
    lastConf = MIN_CONF
    walog = 0.1
    tone = None
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

def outputComposition(composition, outFile=None):
    _log.debug( "outputComposition: outFile: %s" , outFile) 
    if outFile:
        write_Composition(outFile, composition)
    else:
        fluidsynth.play_Composition(composition)
        
def makeBridges(bridge_length, bridge_meter, source_part, target_part):
    source = interpret(source_part._chords[-1], source_part.key)
    target = interpret(target_part._chords[0], target_part.key, True)
    path_options = find_chord_paths(source, target, 5)[:3]
    for path in path_options:
        path_split = part_split(bridge_length, len(path))
        bridge = SongPart(bridge_length, key=source_part.key, meter=source_part.meter)
        start_beat = 0
        for i in range(len(path)):
            bridge.setChords(chords.from_shorthand(path[i]), range(start_beat, start_beat + path_split[i]))
            start_beat += path_split[i]
        #TODO: add melody
        yield bridge
        

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
    parser.add_argument('--beatles','-a', action='store_true', default=False,
                        help='Beatles medley. (default: %(default)s)')
    parser.add_argument('--output', default=None,
                        help='Output file for results. (default: %(default)s)')
    parser.add_argument('--debug', action='store_true')
    options = parser.parse_args()
    if hasattr(options, 'help'):
        sys.exit()
    if options.debug: 
        _log.info( "options:%r", options)
        _debug = 1
        _log.setLevel(logging.DEBUG)
        _log.info( "set logLevel to DEBUG")

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
        for n in getToneStream(loop_size):
            loop.append(n)
        trk = makeTrack(loop, context)
        _log.info( "Track:")
        _log.info( trk)
        
        comp = Composition()
        comp.add_track(trk)
        outputComposition(comp, options.output) 

    if options.blues:
        blueTones = [
        Tone(*x) for x in [
                (64, 0, 1), (67, 1, 1), (72, 2, 2),
                (75, 4, 1), (74, 5, 1), (72, 6, 1), (69, 7, 1), 
                (60, 8, 1), (64, 9, 1), (67, 10, 1), (72, 11, 1), 
                (70, 12, 1), (67, 13, 1), (64, 14, 1), (60, 15, 1), 
                (75, 16, 1), (74, 17, 1), (72, 18, 1), (69, 19, 1), 
                (75, 20, 1), (74, 21, 1), (72, 22, 1), (69, 23, 1), 
                (60, 24, 1), (64, 25, 1), (67, 26, 1), (72, 27, 1), 
                (60, 28, 1), (64, 29, 1), (67, 30, 1), (72, 31, 1), 
                (62, 32, 1), (67, 33, 1), (71, 34, 1), (74, 35, 1), 
                (75, 36, 1), (74, 37, 1), (72, 38, 1), (69, 39, 1), 
                (60, 40, 1), (64, 41, 1), (67, 42, 1), (72, 43, 1), 
                (62, 44, 1), (67, 45, 1), (71, 46, 1), (74, 47, 1)]]
        k = context.key
        A = SongPart(48, key=k, meter=context.meter)
        progression = ['I','IV7','I','I7','IV7','IV7','I','I','V7','IV7','I7','V7']
        A.setBarProgresion(progression)
        A.setTones(blueTones)
        context.addPart('A', A)
        context.appendArrangement('A', 'verse')
        bassPlayer = WalkingBassPlayer(context)
        basePlayer = Player(context)
        bassTrk = bassPlayer.play(0, int(context.total_beats))
        baseTrk = basePlayer.play(0, int(context.total_beats))
        #combine tracks
        comp = Composition()
        comp.add_track(bassTrk)
        comp.add_track(baseTrk)
        outputComposition(comp, options.output)

    if options.beatles:
        ElanorTones = [ Tone(*x) for x in ElanorNotes]
        JudeTones = [ Tone(*x) for x in JudeNotes]
        A = SongPart(36, key='F', meter=(4,4))
        A._chords = []
        for c, l in JudeChords:
            A._chords += l*[chords.from_shorthand(c)]
        A.setTones(JudeTones)
        _log.info( A._track.bars)
        context.addPart('A', A)
        context.appendArrangement('A', 'verse')
        C = SongPart(40, key='D', meter=(4,4))
        C._chords = []
        for c, l in ElanorChords:
            C._chords += l*[chords.from_shorthand(c)]
        C.setTones(ElanorTones)
        B = SongPart(16, key='F', meter=(4,4))
        #TODO: stitch the songs
        source = interpret(A._chords[-1], A.key)
        target = c._chords[0]
        path_options = find_chord_paths(source, target, 5)[:3]
        path_split = part_split(16, n)
        #context.addPart('B', B)
        #context.appendArrangement('B', 'bridge')

        
        
        context.addPart('C', C)
        context.appendArrangement('C', 'verse')
        bassPlayer = ElementaryBassPlayer(context)
        basePlayer = Player(context)
        bassTrk = bassPlayer.play(0, int(context.total_beats))
        baseTrk = basePlayer.play(0, int(context.total_beats))
        #combine tracks
        comp = Composition()
        comp.add_track(bassTrk)
        comp.add_track(baseTrk)
        outputComposition(comp, options.output)
        
    stream.stop_stream()
    stream.close()
    p.terminate()
