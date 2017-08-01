from mingus.core import intervals, chords, notes, keys, scales
from transitions import chord_transitions
from operator import itemgetter

POSITION_WEIGHT = 0.2

def _r_find(start, target, depth):
    """
    start: starting chord in tuple format (root_as_int, shorthand) e.g. (10, 'dom7') is ['Bb', 'D', 'F', 'Ab']
    target: target chord in tuple format
    depth: the maximum depth to search for transitions 
    """
    r = []
    if depth <= 0:
        return r
    if start == target:
        r += [([start], 0)]
    chordx = []
    if start[1] in chord_transitions:
        chordx = chord_transitions[start[1]]
    step_cost = 1
    for next_chord in [((start[0] + delta) % 12, shorthand) for shorthand, delta in chordx]:
        for pp, cost in _r_find(next_chord, target, depth - 1):
            r.append(([start] + pp, cost + step_cost))
        step_cost += POSITION_WEIGHT
    return r


#
# find_chord_paths
#

def find_chord_paths(start, target, depth):
    paths = []
    for p, cost in sorted(_r_find(start, target, depth), key=itemgetter(1)):
        paths.append([notes.int_to_note(c[0]) + c[1] for c in p])
    return paths

# interpret - returns a tuple from the chord in a key compatible with the transitions dict
# adds a 7th if necessary
#

def interpret(chord, key, allow_target=False):
    ch = chord
    # chord has to be a non-inverted, non-polychord
    shorthand = chords.determine(ch, True, True, True)
    if len(shorthand) == 0: 
        raise Exception("Can't interpret chord %s in key %s" % (chord, key))
    shorthand = shorthand[0] #get the most common representation
    #look for the chord type in chord_transitions 
    if (shorthand[len(chord[0]):] in chord_transitions) or ((shorthand[len(chord[0]):] in ['m', 'M']) and allow_target):
        return (notes.note_to_int(chord[0]), shorthand[len(chord[0]):])
    #compute the seventh in this key
    seventh = intervals.interval(key, chord[0], 6)
    #make the seventh chord
    if not seventh in chord:
        ch += [seventh]
    #do it all over again
    shorthand = chords.determine(ch, True, True, True)
    if len(shorthand) == 0:
        raise Exception("Can't interpret chord %s in key %s" % (chord, key))
    shorthand = shorthand[0]
    #all the 7ths are in chord_transitions
    return (notes.note_to_int(chord[0]), shorthand[len(chord[0]):])
#
# split() splits a size into nice power-of-two intervals
#
    
def part_split(size, n):
    ch = 2 ** (int.bit_length(size)-1)
    cn = n / 2
    if n == 1: return [size]
    if ch == size: ch = ch / 2
    return part_split(ch, cn) + part_split(size-ch, n-cn)
#the default scale types to consider when determining scales
default_scales = [
    scales.Major, scales.NaturalMinor, scales.MelodicMinor, 
    scales.HarmonicMajor, scales.HarmonicMinor, scales.WholeTone, 
    scales.Octatonic, scales.Chromatic]

def determineScale(notes, scale_types = default_scales):
    notes = set(notes)
    for scale in scale_types:
        for key in keys.keys:
            if scale.type == 'major':
                if (notes <= set(scale(key[0]).ascending()) or
                        notes <= set(scale(key[0]).descending())):
                    return scale(key[0])
            elif scale.type == 'minor':
                if (notes <= set(scale(keys.get_notes(key[1])[0]).ascending()) or
                        notes <= set(scale(keys.get_notes(key[1])[0]).descending())):
                    return scale(keys.get_notes(key[1])[0])
#
# interpolate returns an array that equals partA when coeffiecient == 0
# and partB whenr coefficient == 1 
#
def interpolate(partA, partB, coefficient):
    if coefficient <= 0.0:
        return partA
    if coefficient >= 1.0:
        return partB
    #make arrays the same length
    while len(partB) < len(partA):
        partB.append(partB[-1])
    while len(partB) > len(partA):
        partA.append(partA[-1])
    xcoefficient = 1.0 - coefficient
    return [(partA[i][0] * xcoefficient + partB[i][0] * coefficient, 
             partA[i][1] * xcoefficient + partB[i][1] * coefficient) for i in range(len(partA))]
