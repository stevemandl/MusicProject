from mingus.containers import Note
from mingus.core.notes import note_to_int

#
# Sieve class
#

class Sieve():
    """ This is the base class for a note sieve, used to find nearby notes that are in a 
        scale or chord"""
    def __init__(self, note_range):
        self._range = note_range
        
    def attune(self, proposed_note, ascending=True):
        """return the closest note to the proposed note
           if possible, in the direction of ascending"""
        if proposed_note in self._range: 
            return Note(proposed_note)
        if proposed_note > max(self._range):
            return self._range[-1]
        if proposed_note < min(self._range):
            return self._range[0]
        previous_note = 0
        for n in self._range:
            if ascending and n > proposed_note:
                return n
            if n > proposed_note:
                return previous_note
            previous_note = n

    def overlay(self, note_range, notes):
        """ overlays the note_range with the note names contained in the notes array
        e.g. overlay(range(Note('C-2'), Note('C-4')), ['C', 'F#']) sets the note range to 
        ['C-2', 'F#-2', 'C-3', 'F#-3', 'C-4'] """
        if hasattr(notes, 'ascending'):
            notes = notes.ascending()
        notes = [note_to_int(n) for n in notes]
        self._range = [Note(n) for n in note_range if note_to_int(Note(n).name) in notes]
            
                