chord_transitions = {
    'sus47' : [('M', -7), ('M7', -7), ('M',2), ('M7',2), ('sus47',3)], 
    'dim7'  : [('M', 1), ('m', 1), ('M7',1), ('mM7', 1), ('sus4',1),
               ('7',-1), ('7',2), ('7',-4), ('7',-7), ('m7b5',0),
               ('m7b5',-3),('m7b5',3),('m7b5',-6)], 
    '7'     : [('M', -7), ('m', -7), ('M7', -7), ('mM7', -7), ('M',-1),
               ('M7', -1), ('m',-1), ('mM7', -1), ('M',2), ('M7',2), 
               ('sus4',-7),('dim7',4)], 
    'aug'   : [('M',0), ('M7',0), ('m',-3), ('mM7',-3), ('m',-7),
               ('mM7',-7), ('M',-4), ('M7',-4), ('m',1), ('mM7',1),
               ('M',4),('M7',4),
               ('M',-7), ('M7',-7), ('m',0), ('mM7',0), ('M',1),
               ('M7',1), ('m',-4), ('mM7',-4), ('M',-3), ('M7',-3),
               ('m',4), ('mM7',4)], 
    'm7'    : [('7',-7), ('7',-1), ('sus47',-7), ('7',0), ('mM7',-5),
               ('M7',-5), ('M7',-4), ('M',-4), ('M7',3), ('M',3), ('m7b5',0)], 
    'sus4'  : [('M',0), ('M7',0), ('m',0), ('mM7',0), ('m7',0)],
    'M7'    : [('m7',-3), ('M',5), ('M7',5), ('m7',2), ('m7b5',2),
               ('7',-5), ('dim7',-1), ('sus47',-5), ('M7',-5), ('7',-2),
               ('7',0), ('sus4',1), ('dim7',1), ('aug',0), ('m7',0), 
               ('m',0), ('mM7',0), ('m',5), ('mM7',5), ('M',-1),
               ('M7',-1), ('m',-1), ('mM7',-1)], 
    'm7b5'  : [('7',-7), ('7',-1), ('M',-1), ('M7',-1), ('m7',3),
               ('dim7',0),('m7',0),('7',2)], 
    'mM7'   : [('m7b5',2), ('m7',5), ('M',-3), ('M7',-3), ('m7b5',-3),
               ('7',-5), ('7',1), ('7',-2), ('aug',-5), ('7',0),
               ('dim7',-1),('sus47',-2),('m7b5',0),('M7',-5),('M7',1)], 
    'sus2'  : [('M',0), ('M7',0), ('m',0), ('mM7',0), ('m7',0)]
    }
#Problem with the sus2 chord above is that we don't know if it's major or minor.  The sus4 is ok because it obscures
#whether it's major/minor until it resolves, but this one is different.  Maybe we should take it out.