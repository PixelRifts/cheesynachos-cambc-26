import sys
import math
import random

from typing import Optional
from enum import Enum
from cambc import Controller, Environment, Position, Direction, EntityType

# Symmetry Functions:

class Symmetry(Enum):
    ROTATIONAL = 'rotational'
    VERTICAL = 'vertical'
    HORIZONTAL = 'horizontal'

def guess_symmetry(width: int, height: int) -> Symmetry:
    if width > height: return Symmetry.HORIZONTAL
    elif height > width: return Symmetry.VERTICAL
    return Symmetry.ROTATIONAL

def get_symmetric(pos: Position, width: int, height: int, sym: Symmetry) -> Position:
    match sym:
        case Symmetry.ROTATIONAL: return Position(width - 1 - pos.x, height - 1 - pos.y)
        case Symmetry.VERTICAL:   return Position(pos.x,             height - 1 - pos.y)
        case Symmetry.HORIZONTAL: return Position(width - 1 - pos.x, pos.y             )
    assert False

# Adjacent direction queries

def get_best_pathable_adj_with_diag(rc: Controller, pos: Position, heu: Position) -> Direction:
    best_dist = 1000000
    best_dir = Direction.CENTRE
    for d in DIRECTIONS:
        p = pos.add(d)
        if not is_in_map(p, rc.get_map_width(), rc.get_map_height()): continue
        if not rc.is_in_vision(p): continue
        if not is_pos_pathable(rc, p): continue
        if is_friendly_transport(rc, p): continue
        bb = rc.get_tile_builder_bot_id(p)
        if bb is not None: continue
        dist = p.distance_squared(heu)
        if dist < best_dist:
            best_dist = dist
            best_dir = d
    return best_dir