import sys

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
pf_state = PFState()

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

# This is a 2 tier-ed approach, that I implemented for MIT Battlecode translated to python
# Could have bugs, subject to change
def pathfind_to(rc: Controller, target: Position):
    global pf_state

    if pf_state.final_target != target:
        pf_state.final_target = target
        pf_state.virtual_target = rc.get_position()
        
        pf_state.should_bug = False
        pf_state.best_bug_dist = float('inf')
        pf_state.bug_dir = None
        pf_state.should_guess_rotation = True
    
    if rc.get_position() == pf_state.virtual_target:
        recompute_virtual_target(rc)

    pathfind_to_virtual(rc)

def recompute_virtual_target(rc: Controller):
    global pf_state

    current: Position = pf_state.virtual_target
    
    steps = 0
    while rc.is_in_vision(current) and steps < 4:
        # Stop if reached goal
        if current == pf_state.final_target:
            break
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
            new_loc = current.add(pf_state.bug_dir)
            if not virtually_navvable(rc, new_loc):
                for _ in range(8):
                    pf_state.bug_dir = pf_state.bug_dir.rotate_right() if pf_state.clockwise else pf_state.bug_dir.rotate_left()
                    new_loc = current.add(pf_state.bug_dir)
                    if virtually_navvable(rc, current.add(pf_state.bug_dir)):
                        break
            
            if not virtually_navvable(rc, new_loc):
                break

            current = new_loc
            pf_state.bug_dir = pf_state.bug_dir.rotate_right() if not pf_state.clockwise else pf_state.bug_dir.rotate_left()
            
            # Circumnav mode exit condition
            d = current.distance_squared(pf_state.final_target)
            if d < pf_state.best_bug_dist:
                pf_state.should_bug = False
            
            print("Bug mode: ", current, file=sys.stderr)
        else:
            # Greedy
            closest = current.distance_squared(pf_state.final_target)
            best = current
            print("[", file=sys.stderr)
            for d in DIRECTIONS:
                if virtually_navvable(rc, current.add(d)):
                    nxt = current.add(d)
                    dist = nxt.distance_squared(pf_state.final_target)
                    print("  ", d, "  ", nxt, " - dist - ", dist, ", ", file=sys.stderr)
                    if dist < closest:
                        closest = dist
                        best = nxt
            print("]", file=sys.stderr)
            
            if best != current:
                current = best
            else:
                pf_state.should_bug = True
                pf_state.best_bug_dist = current.distance_squared(pf_state.final_target)
                pf_state.bug_dir = current.direction_to(pf_state.final_target)
                pf_state.should_guess_rotation = True
            
            print("Greedy: ", current, file=sys.stderr)
        
        rc.draw_indicator_dot(current, 50, 180, 50)
    
    pf_state.virtual_target = current
    print(pf_state.virtual_target, file=sys.stderr)
    rc.draw_indicator_dot(pf_state.virtual_target, 50, 255, 50)

def pathfind_to_virtual(rc: Controller):
    global pf_state

def virtually_navvable(rc: Controller, pos: Position):
    return rc.is_in_vision(pos) and rc.is_tile_empty(pos)