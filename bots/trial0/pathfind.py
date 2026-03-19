import sys

from collections import deque
from cambc import Controller, Direction, EntityType, Environment, Position

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

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]
CARDINAL_DIRECTIONS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

# This is a 2 tier-ed approach, that I implemented for MIT Battlecode translated to python
# Could have bugs, subject to change
def fast_pathfind_to(rc: Controller, target: Position):
    global pf_state

    rc.draw_indicator_line(rc.get_position(), target, 0, 128, 0)
    if pf_state.final_target != target:
        pf_state.reset()
        pf_state.final_target = target
        pf_state.virtual_target = rc.get_position()
        
    if rc.get_position() == target:
        return

    if rc.get_position().distance_squared(target) == 1:
        if rc.can_move(rc.get_position().direction_to(target)):
            rc.move(rc.get_position().direction_to(target))
            return

    if rc.get_position() == pf_state.virtual_target:
        pf_state.bug_cooldown = 4
        recompute_fast_virtual_target(rc)
    else:
        pf_state.bug_cooldown -= 1
    
    if pf_state.bug_cooldown <= 0:
        pf_state.virtual_target = rc.get_position()
        pf_state.should_bug = False
        return

    fast_pathfind_to_virtual(rc)


def recompute_fast_virtual_target(rc: Controller):
    global pf_state

    current: Position = pf_state.virtual_target

    # print("Round", rc.get_current_round(), file=sys.stderr)
    
    steps = 0
    while rc.is_in_vision(current) and steps < 3:
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


def fast_pathfind_to_virtual(rc: Controller):
    global pf_state
    
    my_loc = rc.get_position()
    goal = pf_state.virtual_target

    best_dir = None
    best_score = float('-inf')

    to_goal = my_loc.direction_to(goal)

    if my_loc == goal:
        return

    for d in DIRECTIONS:
        target = my_loc.add(d)

        # If we can sense the tile
        if (is_in_map(target, rc.get_map_width(), rc.get_map_height())) and\
            rc.is_in_vision(target):
            if rc.get_tile_env(target) == Environment.WALL:
                continue
            if rc.get_tile_builder_bot_id(target) is not None:
                continue
        else:
            continue

        # Base score: closer to goal is better
        score = -(target.distance_squared(goal) * 50)

        # Flow heuristic (look ahead 3 tiles)
        flow_score = 0
        test = target
        for _ in range(3):
            test = test.add(to_goal)
            if (is_in_map(test, rc.get_map_width(), rc.get_map_height())) and\
               (rc.is_in_vision(test) and rc.get_tile_env(test) == Environment.WALL):
                angle = degrees_between(d, to_goal)

                if angle == 90:
                    flow_score += 60
                elif angle == 0:
                    flow_score -= 40
                break

        score += flow_score

        if score > best_score:
            best_score = score
            best_dir = d

    if best_dir:
        best_pos = rc.get_position().add(best_dir)
        if rc.can_move(best_dir):
            rc.move(best_dir)
        elif rc.can_build_road(best_pos):
            rc.build_road(best_pos)
            if rc.can_move(best_dir):
                rc.move(best_dir)
    else:
        # fallback: reset pathing
        pf_state.virtual_target = my_loc
    

# === Building Conveyors ===

def cardinal_pathfind_to(rc: Controller, target: Position, home: Position):
    global pf_state

    rc.draw_indicator_line(rc.get_position(), target, 0, 128, 0)
    if pf_state.final_target != target:
        pf_state.reset()
        pf_state.final_target = target
        pf_state.virtual_target = rc.get_position()
    
    if rc.get_position() == target:
        return

    if rc.get_position().distance_squared(target) == 1:
        if rc.can_move(rc.get_position().direction_to(target)):
            rc.move(rc.get_position().direction_to(target))
            return

    if rc.get_position() == pf_state.virtual_target:
        pf_state.bug_cooldown = 4
        recompute_cardinal_virtual_target(rc)
    else:
        pf_state.bug_cooldown -= 1
    
    if pf_state.bug_cooldown <= 0:
        pf_state.virtual_target = rc.get_position()
        pf_state.should_bug = False
        return

    cardinal_pathfind_to_virtual(rc, Direction.EAST)


def recompute_cardinal_virtual_target(rc: Controller):
    global pf_state

    current: Position = pf_state.virtual_target

    # print("Round", rc.get_current_round(), file=sys.stderr)
    
    steps = 0
    while rc.is_in_vision(current) and steps < 3:
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
                    if cardinal_virtually_navvable(rc, current.add(dirL), dirL):
                        break
                    dirL = dirL.rotate_left().rotate_left()
                locL = current.add(dirL)
                
                dirR: Direction = pf_state.bug_dir
                for _ in range(8):
                    if cardinal_virtually_navvable(rc, current.add(dirR), dirR):
                        break
                    dirR = dirR.rotate_right()
                locR = current.add(dirR)

                pf_state.clockwise = locL.distance_squared(pf_state.final_target) >= locR.distance_squared(pf_state.final_target)

            # Try to find wall-follow dir
            current_loc: Position = None
            new_loc: Position = current.add(pf_state.bug_dir)
            picked_dir: Direction = pf_state.bug_dir

            if cardinal_virtually_navvable(rc, new_loc, pf_state.bug_dir):
                current_loc = new_loc
            else:
                break_flag = False
                for _ in range(8):
                    candidate_dir = pf_state.bug_dir.rotate_right() if pf_state.clockwise else pf_state.bug_dir.rotate_left()
                    new_loc = current.add(candidate_dir)
                    if cardinal_virtually_navvable(rc, new_loc, candidate_dir):
                        current_loc = new_loc
                        picked_dir = candidate_dir
                        break
                    elif not is_in_map(new_loc, rc.get_map_width(), rc.get_map_height()):
                        pf_state.clockwise = not pf_state.clockwise
                        break_flag = True
                        break
                    pf_state.bug_dir = candidate_dir

                if break_flag:
                    break

            if current_loc is not None:
                if not is_in_map(current_loc, rc.get_map_width(), rc.get_map_height()):
                    break
                assert current_loc != current
                current = current_loc
                
                if not CARDINAL_DIRECTIONS.__contains__(picked_dir):
                    steps += 1
                
                pf_state.bug_dir = pf_state.bug_dir.rotate_right() if not pf_state.clockwise else pf_state.bug_dir.rotate_left()
                d = current.distance_squared(pf_state.final_target)
                if d < pf_state.best_bug_dist:
                    pf_state.should_bug = False

            # print("Bug mode: ", current, file=sys.stderr)
        else:
            # Greedy
            closest = current.distance_squared(pf_state.final_target)
            best = current
            for d in CARDINAL_DIRECTIONS:
                if cardinal_virtually_navvable(rc, current.add(d), d):
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
                pf_state.bug_dir = cardinal_direction_to(current, pf_state.final_target)
                pf_state.should_guess_rotation = False
            
            # print("Greedy: ", current, file=sys.stderr)
        
        rc.draw_indicator_dot(current, 50, 180, 50)
    
    pf_state.virtual_target = current
    # print(pf_state.virtual_target, file=sys.stderr)
    rc.draw_indicator_dot(pf_state.virtual_target, 50, 255, 50)


def cardinal_pathfind_to_virtual(rc: Controller, going_home: bool):
    global pf_state
    
    my_loc = rc.get_position()
    goal = pf_state.virtual_target

    best_dir = None
    best_score = float('-inf')

    to_goal = cardinal_direction_to(my_loc, goal)

    if my_loc == goal:
        return

    for d in CARDINAL_DIRECTIONS:
        target = my_loc.add(d)

        # If we can sense the tile
        if (is_in_map(target, rc.get_map_width(), rc.get_map_height())) and\
            rc.is_in_vision(target):
            if rc.get_tile_env(target) == Environment.WALL:
                continue
            if rc.get_tile_builder_bot_id(target) is not None:
                continue
        else:
            continue

        # Base score: closer to goal is better
        score = -(target.distance_squared(goal) * 50)

        # Can add other heuristics

        if score > best_score:
            best_score = score
            best_dir = d

    if best_dir:
        best_pos = rc.get_position().add(best_dir)
        conveyor_dir = best_dir.opposite() if going_home else best_dir
        if rc.can_move(best_dir):
            rc.move(best_dir)
        elif rc.can_build_conveyor(best_pos, conveyor_dir):
            rc.build_conveyor(best_pos, conveyor_dir)
            if rc.can_move(best_dir):
                rc.move(best_dir)
    else:
        # fallback: reset pathing
        pf_state.virtual_target = my_loc
    

# === Helpers === (Maybe move to helpers.py)

def is_in_map(pos: Position, width, height) -> bool:
    return pos.x >= 0 and pos.x < width and pos.y >= 0 and pos.y < height

def cardinal_virtually_navvable(rc: Controller, pos: Position, incoming_dir: Direction) -> bool:
    if not is_in_map(pos, rc.get_map_width(), rc.get_map_height()):
        return False
    if not rc.is_in_vision(pos):
        return True
    
    if CARDINAL_DIRECTIONS.__contains__(incoming_dir):
        return actually_navvable(rc, pos) or rc.get_tile_builder_bot_id(pos) is not None
    else:
        (dx, dy) = incoming_dir.opposite().delta()
        prev = pos.add(incoming_dir.opposite())
        test0 = prev.add(Direction.WEST  if dx == 1 else Direction.EAST)
        test1 = prev.add(Direction.NORTH if dx == 1 else Direction.SOUTH)

        if not (is_in_map(test0, rc.get_map_width(), rc.get_map_height()) and is_in_map(test1, rc.get_map_width(), rc.get_map_height())):
            return False
        if not (rc.is_in_vision(test0) and rc.is_in_vision(test1)):
            return True
        if (rc.get_tile_env(test0) == Environment.WALL and rc.get_tile_env(test1) == Environment.WALL):
            return False
        return actually_navvable(rc, pos) or rc.get_tile_builder_bot_id(pos) is not None


def virtually_navvable(rc: Controller, pos: Position) -> bool:
    if not is_in_map(pos, rc.get_map_width(), rc.get_map_height()):
        return False
    return ((not rc.is_in_vision(pos)) or (actually_navvable(rc, pos) or rc.get_tile_builder_bot_id(pos) is not None))

def actually_navvable(rc: Controller, pos: Position) -> bool:
    return is_in_map(pos, rc.get_map_width(), rc.get_map_height()) and\
           rc.is_in_vision(pos) and (rc.is_tile_empty(pos) or rc.is_tile_passable(pos))

DIRECTIONS_ORDERED = [
    Direction.NORTH, Direction.NORTHEAST, Direction.EAST, Direction.SOUTHEAST,
    Direction.SOUTH, Direction.SOUTHWEST, Direction.WEST, Direction.NORTHWEST
]
DIRECTIONS_INDEX = {d: i for i, d in enumerate(DIRECTIONS_ORDERED)}

def degrees_between(d1, d2):
    if d1 == Direction.CENTRE or d2 == Direction.CENTRE:
        return 0

    diff = abs(DIRECTIONS_INDEX[d1] - DIRECTIONS_INDEX[d2])
    if diff > 4:
        diff = 8 - diff

    return diff * 45

def cardinal_direction_to(me: Position, other: Position) -> Direction:
    dx = other.x - me.x
    dy = other.y - me.y

    if dx == 0 and dy == 0:
        return Direction.CENTRE

    if abs(dx) > abs(dy):
        return Direction.EAST if dx > 0 else Direction.WEST
    else:
        return Direction.SOUTH if dy > 0 else Direction.NORTH