from mingus.core import intervals, chords, notes
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

def interpret(chord, key):
    ch = chord
    shorthand = chords.determine(ch, True, True, True)
    if len(shorthand) == 0:
        raise Exception("Can't interpret chord %s in key %s" % (chord, key))
    shorthand = shorthand[0]
    if shorthand[len(chord[0]):] in chord_transitions:
        return (notes.note_to_int(chord[0]), shorthand[len(chord[0]):])
    seventh = intervals.interval(key, chord[0], 6)
    if not seventh in chord:
        ch += [seventh]
    shorthand = chords.determine(ch, True, True, True)
    if len(shorthand) == 0:
        raise Exception("Can't interpret chord %s in key %s" % (chord, key))
    shorthand = shorthand[0]
    return (notes.note_to_int(chord[0]), shorthand[len(chord[0]):])
    
    
