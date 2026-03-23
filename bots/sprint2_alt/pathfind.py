import sys

from helpers import is_pos_pathable, degrees_between, cardinal_direction_to, is_in_map, DIRECTIONS, CARDINAL_DIRECTIONS
from collections import deque
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants

# Implement BUG + BFS Pathfinding
class PFState:
    def __init__(self):
        self.virtual_target = Position(0, 0)
        self.final_target = Position(0, 0)
        self.should_bug = False
        self.best_bug_dist = float('inf')
        self.bug_dir = None
        self.should_guess_rotation = True
        self.clockwise = False
        self.bug_cooldown = 4
        
    def reset(self):
        self.virtual_target = Position(0, 0)
        self.final_target = Position(0, 0)
        self.should_bug = False
        self.best_bug_dist = float('inf')
        self.bug_dir = None
        self.should_guess_rotation = True
        self.clockwise = False
        self.bug_cooldown = 4
pf_state = PFState()


# This is a 2 tier-ed approach, that I implemented for MIT Battlecode translated to python
# Could have bugs, subject to change
def fast_pathfind_to(rc: Controller, target: Position):
    global pf_state

    if pf_state.final_target != target:
        pf_state.reset()
        pf_state.final_target = target
        pf_state.virtual_target = rc.get_position()
        
    if rc.get_position() == target:
        return True

    if rc.get_position().distance_squared(target) == 1:
        if rc.can_move(rc.get_position().direction_to(target)):
            rc.move(rc.get_position().direction_to(target))
            return True

    if rc.get_position() == pf_state.virtual_target:
        pf_state.bug_cooldown = 4
        recompute_fast_virtual_target(rc)
    else:
        pf_state.bug_cooldown -= 1
    
    if pf_state.bug_cooldown <= 0:
        pf_state.virtual_target = rc.get_position()
        pf_state.should_bug = False
        return False

    fast_pathfind_to_virtual(rc)
    if rc.get_position() == target:
        return True
    
    # rc.draw_indicator_line(rc.get_position(), target, 0, 128, 0)
    return False


def recompute_fast_virtual_target(rc: Controller):
    global pf_state

    current: Position = pf_state.virtual_target

    # print("Round", rc.get_current_round(), file=sys.stderr)
    
    steps = 0
    while rc.is_in_vision(current) and steps < 2:
        # Stop if reached goal
        if current == pf_state.final_target:
            break
        # print("Iter --", current, file=sys.stderr)

        steps += 1

        if pf_state.should_bug:
            # Run Bug 1.5

            # Guess which way to turn while circumnavving
            if pf_state.should_guess_rotation:
                pf_state.should_guess_rotation = False

                dirL: Direction = pf_state.bug_dir
                for _ in range(8):
                    if virtually_navvable(rc, current.add(dirL)):
                        break
                    dirL = dirL.rotate_left()
                locL = current.add(dirL)
                
                dirR = pf_state.bug_dir
                for _ in range(8):
                    if virtually_navvable(rc, current.add(dirR)):
                        break
                    dirR = dirR.rotate_right()
                locR = current.add(dirR)

                pf_state.clockwise = locL.distance_squared(pf_state.final_target) >= locR.distance_squared(pf_state.final_target)

            # Try to find wall-follow dir
            current_loc: Position = None
            new_loc: Position = current.add(pf_state.bug_dir)
            if virtually_navvable(rc, new_loc):
                current_loc = new_loc
            else:
                break_flag = False
                for _ in range(8):
                    new_loc = current.add(pf_state.bug_dir.rotate_right() if pf_state.clockwise else pf_state.bug_dir.rotate_left())
                    if virtually_navvable(rc, new_loc):
                        current_loc = new_loc
                        break
                    elif not is_in_map(new_loc, rc.get_map_width(), rc.get_map_height()):
                        pf_state.clockwise = not pf_state.clockwise
                        break_flag = True
                        break
                    pf_state.bug_dir = pf_state.bug_dir.rotate_right() if pf_state.clockwise else pf_state.bug_dir.rotate_left()

                if break_flag:
                    break

            if current_loc is not None:
                if not is_in_map(current_loc, rc.get_map_width(), rc.get_map_height()):
                    break
                assert current_loc != current
                current = current_loc
                pf_state.bug_dir = pf_state.bug_dir.rotate_right() if not pf_state.clockwise else pf_state.bug_dir.rotate_left()
                d = current.distance_squared(pf_state.final_target)
                if d < pf_state.best_bug_dist:
                    pf_state.should_bug = False

            # print("Bug mode: ", current, file=sys.stderr)
        else:
            # Greedy
            closest = current.distance_squared(pf_state.final_target)
            best = current
            for d in DIRECTIONS:
                if virtually_navvable(rc, current.add(d)):
                    nxt = current.add(d)
                    dist = nxt.distance_squared(pf_state.final_target)
                    if dist < closest:
                        closest = dist
                        best = nxt

            if not rc.is_in_vision(best):
                break
            
            if best != current:
                current = best
            else:
                pf_state.should_bug = True
                pf_state.best_bug_dist = current.distance_squared(pf_state.final_target)
                pf_state.bug_dir = current.direction_to(pf_state.final_target)
                pf_state.should_guess_rotation = False
            
            # print("Greedy: ", current, file=sys.stderr)
        
        rc.draw_indicator_dot(current, 50, 180, 50)
    
    pf_state.virtual_target = current
    # print(pf_state.virtual_target, file=sys.stderr)
    rc.draw_indicator_dot(pf_state.virtual_target, 50, 255, 50)


# def fast_pathfind_to_virtual(rc: Controller):
#     global pf_state
    
#     my_loc = rc.get_position()
#     goal = pf_state.virtual_target

#     best_dir = None
#     best_score = float('-inf')

#     to_goal = my_loc.direction_to(goal)

#     if my_loc == goal:
#         return

#     for d in DIRECTIONS:
#         target = my_loc.add(d)

#         if not actually_navvable(rc, target):
#             continue

#         # Base score: closer to goal is better
#         score = -(target.distance_squared(goal) * 50)
#         if score > best_score:
#             best_score = score
#             best_dir = d

#     if best_dir:
#         best_pos = rc.get_position().add(best_dir)
#         if rc.can_destroy(best_pos) and should_destroy(rc, best_pos):
#             rc.destroy(best_pos)
#         if rc.can_move(best_dir):
#             rc.move(best_dir)
#         elif rc.can_build_road(best_pos):
#             rc.build_road(best_pos)
#             if rc.can_move(best_dir):
#                 rc.move(best_dir)
#     else:
#         # fallback: reset pathing
#         pf_state.virtual_target = my_loc

def fast_pathfind_to_virtual(rc: Controller):
    global pf_state

    my_loc = rc.get_position()
    goal = pf_state.virtual_target

    if my_loc == goal:
        return

    width = rc.get_map_width()
    height = rc.get_map_height()

    q = deque([goal])
    visited = {goal}
    parent = {}

    found = False

    while q:
        cur = q.popleft()

        if cur == my_loc:
            found = True
            break

        for d in DIRECTIONS:
            nxt = cur.add(d)

            if nxt in visited:
                continue
            if not actually_navvable(rc, nxt):
                continue

            visited.add(nxt)
            parent[nxt] = cur
            q.append(nxt)

    if not found:
        pf_state.virtual_target = my_loc
        return

    best_pos = parent[my_loc]
    best_dir = my_loc.direction_to(best_pos)

    if rc.can_destroy(best_pos) and should_destroy(rc, best_pos):
        rc.destroy(best_pos)

    if rc.can_move(best_dir):
        rc.move(best_dir)
    elif rc.can_build_road(best_pos):
        rc.build_road(best_pos)
        if rc.can_move(best_dir):
            rc.move(best_dir)
    

def virtually_navvable(rc: Controller, pos: Position) -> bool:
    if not is_in_map(pos, rc.get_map_width(), rc.get_map_height()) or not rc.is_in_vision(pos):
        return False
    return ((rc.get_tile_builder_bot_id(pos) is not None) or is_pos_pathable(rc, pos))

def should_destroy(rc: Controller, pos: Position) -> bool:
    bldg = rc.get_tile_building_id(pos)
    if bldg is None: return False
    entt = rc.get_entity_type(bldg)
    # TODO maybe add more things that should be destroyed here
    return entt == EntityType.MARKER

def actually_navvable(rc: Controller, pos: Position) -> bool:
    if not is_in_map(pos, rc.get_map_width(), rc.get_map_height()) or not rc.is_in_vision(pos):
        return False
    return is_pos_pathable(rc, pos)
