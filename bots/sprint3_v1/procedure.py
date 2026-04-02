import pathfind
from sense import *

from cambc import Controller, Environment, Position, Direction, EntityType

def try_destroy(rc: Controller, sense: Sense, me: Position, p: Position) -> bool:
    if not sense.is_seen(p):
        pathfind.fast_pathfind_to(rc, p)
        return False
    
    bldg = rc.get_tile_building_id(p)
    if bldg is None:
        if me is None: return True
        return pathfind.fast_pathfind_to(rc, sense, me)

    entt = sense.get_entity(p)
    allied = sense.is_allied(p)
    already_connected = False

    if entt in ENTITY_UNWALKABLE:
        if allied:
            if rc.get_position() == p:
                pathfind.fast_pathfind_to(rc, sense, p.add(get_best_empty_adj(rc, p, me)))
            if not is_adjacent_with_diag(rc.get_position(), p):
                pathfind.fast_pathfind_to(rc, sense, p)
            if rc.can_destroy(p):
                rc.destroy(p)
        else:
            print('cant destroy', p)
    else:
        if allied:
            if rc.can_destroy(p):
                rc.destroy(p)
        else:
            if rc.get_position() != p:
                pathfind.fast_pathfind_to(rc, sense, p)
                if rc.get_position() != p: return False
            if rc.can_fire(p):
                rc.fire(p)

    return False
