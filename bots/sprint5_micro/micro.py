import sys
import sense
import pathfind
import random
import heapq

from bot import Bot
from helpers import *
from procedure import *

from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants, ResourceType

DISTANCE_SCORE_LUT = [ 0, -10, -15, -18, -20 ]

def score_poi(rc: Controller, sense: sense.Sense, poi: Position) -> int:
    my_pos = rc.get_position()
    score = 0
    
    # TODO: Change to A* path length
    distance_index = min(my_pos.chebyshev_distance(poi), len(DISTANCE_SCORE_LUT) - 1)
    score += DISTANCE_SCORE_LUT[distance_index]
    
    return score

