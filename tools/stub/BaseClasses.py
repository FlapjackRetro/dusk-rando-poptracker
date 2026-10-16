import enum
class ItemClassification(enum.IntFlag):
    filler=0; progression=1; useful=2; trap=4
class Item:
    def __init__(self,*a,**k): pass
class Location: pass
class Region: pass
class CollectionState: pass
class Tutorial:
    def __init__(self,*a,**k): pass
