import sys
import math
import random
from cambc import Controller, Environment, Position, Direction, EntityType

RANDOM_SEED = 1234

def is_in_map(pos: Position, width, height) -> bool:
    return pos.x >= 0 and pos.x < width and pos.y >= 0 and pos.y < height

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]
CARDINAL_DIRECTIONS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
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

def biased_random_dir(rc: Controller) -> Direction:
    c = random.randint(0, 10)
    if c < 3:
        return rc.get_position().direction_to(Position(rc.get_map_width() // 2, rc.get_map_height() // 2))
    return random.choice(DIRECTIONS)

def is_adjacent(a: Position, b: Position, debug: bool = False) -> bool:
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    if debug: print(dx, dy, dx + dy == 1, file=sys.stderr)
    return dx + dy == 1