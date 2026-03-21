import sys
import pathfind
import random

import sense
import visualize
from helpers import is_adjacent, cardinal_direction_to, biased_random_dir, is_in_map, DIRECTIONS, CARDINAL_DIRECTIONS

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants

EXPLORE_TIMEOUT = 16
NUKE_WAIT_FOR = 500 # Wait 600 turns before starting to nuke

class BotJob(Enum):
    ECONOMY = "Economy"
    DEFENCE = "Defence"

class BotState(Enum):
    # States for Econ Job
    ECON_EXPLORE = "Explore" # Random Movement until things of importance are seen
    ECON_TARGET  = "Target"  # Unclaimed ore spotted, Moving towards it
    ECON_CONNECT = "Connect" # Connecting Unclaimed ore to core
    ECON_ENSURE  = "Ensure"  # Ensuring validity of conveyor path
    ECON_NUKE    = "Nuke"    # Trying this out, go and destroy opponent conveyor/bridge that is free

    # States for Defece Job
    DEF_CORE_DEFENCE = "Core Defence"
    DEF_TODO = "Todo"

class BuilderBot(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.job = BotJob.ECONOMY
        self.state_turn_counter = 0

        # Sometimes we check defence 1 in five
        if self.rc.get_current_round()%5 ==  1:
            self.state = BotState.DEF_CORE_DEFENCE
        else:
            self.state = BotState.ECON_EXPLORE

        self.sense = sense.Sense(rc)
        self.pathfind_target = None
        
        buildings = rc.get_nearby_buildings(3)
        for b in buildings:
            if rc.get_entity_type(b) == EntityType.CORE:
                self.core_pos = rc.get_position(b)
                break
        
        self.explore_dir = self.core_pos.direction_to(rc.get_position())
        self.explore_timeout = EXPLORE_TIMEOUT
        self.explore_ore_target = None
        self.explore_blacklist = []
        self.connect_harvester_added = False
        self.connect_current_target = None
        self.connect_current = []

    def start_turn(self):
        self.sense.update()

    def turn(self):
        match self.state:
            case BotState.ECON_EXPLORE:
                self.econ_explore()
            case BotState.ECON_TARGET:
                self.econ_target()
            case BotState.ECON_CONNECT:
                self.econ_connect()
            case BotState.ECON_ENSURE:
                self.econ_ensure()
            case BotState.ECON_NUKE:
                self.econ_nuke()

            case BotState.DEF_CORE_DEFENCE:
                self.check_core_defence()
            case BotState.DEF_TODO:
                pass
        
        # pathfind.cardinal_pathfind_to(self.rc, Position(6, 7), False)

    def end_turn(self):
        # Compute symmetry if time left
        # DEBUG: sensing
        # visualize.visualize_map_minimal(self.rc, self.sense)
        print(self.state)
        self.state_turn_counter += 1

    # Econ Turns
    def econ_explore(self):
        # Check for ore
        if self.should_connect_to_ore(self.sense.nearest_ore):
            best_one_off = None
            best_dist = float('inf')
            tested = 0
            for cd in CARDINAL_DIRECTIONS:
                p = self.sense.nearest_ore.add(cd)
                print('trying dir ', cd, end=' ')
                if not self.rc.is_in_vision(p):
                    continue
                tested += 1
                if not (self.sense.is_empty(p) or self.sense.get_building_type(p) == EntityType.ROAD):
                    continue
                dist = p.distance_squared(self.core_pos)
                if dist < best_dist:
                    best_dist = dist
                    best_one_off = cd

            if best_one_off is None:
                if tested != 4: self.explore_blacklist.append(self.sense.nearest_ore)
                return
            
            self.state_turn_counter = 0
            self.state = BotState.ECON_TARGET
            self.explore_ore_target = self.sense.nearest_ore
            self.pathfind_target = self.sense.nearest_ore.add(best_one_off)
            return

        if self.sense.nearest_enemy_infra is not None:
            # TODO Check nukability
            test = random.randint(0, 10)
            if self.rc.get_current_round() > NUKE_WAIT_FOR and test <= 4:
                self.state_turn_counter = 0
                self.state = BotState.ECON_NUKE
                self.pathfind_target = self.sense.nearest_enemy_infra

        # Actual Movement
        self.explore_timeout -= 1
        if self.explore_timeout == 0:
            self.explore_timeout = EXPLORE_TIMEOUT
            self.explore_dir = biased_random_dir(self.rc)
            
        next_pos = self.rc.get_position().add(self.explore_dir)
        if not pathfind.is_in_map(next_pos, self.rc.get_map_width(), self.rc.get_map_height()):
            self.explore_dir = biased_random_dir(self.rc)
            return

        if self.rc.can_move(self.explore_dir):
            self.rc.move(self.explore_dir)
        elif self.rc.is_tile_empty(next_pos):
            if self.rc.can_build_road(next_pos):
                self.rc.build_road(next_pos)
                if self.rc.can_move(self.explore_dir):
                    self.rc.move(self.explore_dir)
        else:
            self.explore_dir = biased_random_dir(self.rc)


    def econ_target(self):
        if self.sense.get_building_type(self.explore_ore_target) == EntityType.HARVESTER:
            self.state_turn_counter = 0
            self.state = BotState.ECON_EXPLORE
            self.explore_dir = self.core_pos.direction_to(self.rc.get_position())
            self.explore_timeout = EXPLORE_TIMEOUT
            self.explore_ore_target = None
            return

            
        if not is_adjacent(self.rc.get_position(), self.explore_ore_target):
            pathfind.fast_pathfind_to(self.rc, self.pathfind_target)
        else:
            self.state_turn_counter = 0
            self.state = BotState.ECON_CONNECT
            self.connect_current_target = None
            self.connect_harvester_added = False
            self.connect_current = []
            self.pathfind_target = None
        
    
    def econ_connect(self):
        if self.connect_harvester_added == False:
            # print(self.rc.get_id(), 'trying to check to place harvester ', self.explore_ore_target, end=': ', file=sys.stderr)
            

            bldg = self.rc.get_tile_building_id(self.explore_ore_target)
            if bldg is not None:
                entt = self.rc.get_entity_type(bldg)
                # print('trace0', entt, end=';', file=sys.stderr)
                match entt:
                    case EntityType.HARVESTER:
                        if self.rc.get_team(bldg) == self.rc.get_team():
                            self.explore_blacklist.append(self.explore_ore_target)
                            self.state_turn_counter = 0
                            self.state = BotState.ECON_EXPLORE
                            self.explore_dir = self.core_pos.direction_to(self.rc.get_position())
                            self.explore_timeout = EXPLORE_TIMEOUT
                            self.explore_ore_target = None
                            return
                        else:
                            # print('FAILED (enemy harvester exists)', self.explore_ore_target, file=sys.stderr)
                            return
                    case EntityType.ROAD | EntityType.MARKER:
                        # print('FAILED (road exists)', self.explore_ore_target, file=sys.stderr)
                        if self.rc.can_destroy(self.explore_ore_target):
                            self.rc.destroy(self.explore_ore_target)
                    case _:
                        # print('FAILED (', entt, ' exists)', self.explore_ore_target, file=sys.stderr)
                        return

            if self.rc.can_build_harvester(self.explore_ore_target):
                # print('placing harvester ', self.explore_ore_target, file=sys.stderr)
                self.rc.build_harvester(self.explore_ore_target)
                self.connect_harvester_added = True
            # else:
                # print('couldnt place harvester at ', self.explore_ore_target, 'from ', self.rc.get_position())
            return
        
        if self.connect_current_target is None or self.rc.get_position() == self.connect_current_target:
            if self.sense.get_building_type(self.rc.get_position()) == EntityType.ROAD and self.rc.can_destroy(self.rc.get_position()):
                self.rc.destroy(self.rc.get_position())
                
            (best_target, final_one) = self.compute_best_bridge_target()
            if self.rc.can_build_bridge(self.rc.get_position(), best_target):
                self.rc.build_bridge(self.rc.get_position(), best_target)
                self.connect_current.append(self.rc.get_position())
            else:
                # print('best_target=',best_target, file=sys.stderr)
                return
            self.connect_current_target = best_target

            if final_one:
                self.state_turn_counter = 0
                self.state = BotState.ECON_EXPLORE
                self.explore_dir = self.core_pos.direction_to(self.rc.get_position())
                self.explore_timeout = EXPLORE_TIMEOUT
                self.explore_ore_target = None
                return

        else:
            pathfind.fast_pathfind_to(self.rc, self.connect_current_target)

    def econ_ensure(self):
        pass

    def econ_nuke(self):
        if pathfind.fast_pathfind_to(self.rc, self.pathfind_target):
            self.rc.self_destruct()

    def check_core_defence(self):
        corners = [
            self.core_pos.add(Direction.NORTHEAST).add(Direction.NORTHEAST),
            self.core_pos.add(Direction.NORTHWEST).add(Direction.NORTHWEST),
            self.core_pos.add(Direction.SOUTHEAST).add(Direction.SOUTHEAST),
            self.core_pos.add(Direction.SOUTHWEST).add(Direction.SOUTHWEST)
        ]

        current_pos = self.rc.get_position()
        for cor in corners:
            self.rc.draw_indicator_dot(cor, 0, 0, 255)

        target_corner = None
        for corner in corners:
            if self.rc.is_in_vision(corner):
                if self.rc.get_tile_building_id(corner) is None:
                    target_corner = corner
                    break

        self.rc.draw_indicator_dot(cor, 255, 0, 0)
        if target_corner:
            if self.rc.can_build_launcher(target_corner):
                self.rc.build_launcher(target_corner)
            elif current_pos != target_corner:
                pathfind.fast_pathfind_to(self.rc, target_corner)
        else:
            self.state = BotState.ECON_EXPLORE

    def compute_best_bridge_target(self) -> (Position, bool):
        rc = self.rc
        start = rc.get_position()
        core = self.core_pos

        width, height = rc.get_map_width(), rc.get_map_height()

        # --- collect core 3x3 tiles --- TODO probably cache
        core_tiles = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                ct = Position(core.x + dx, core.y + dy)
                if is_in_map(ct, width, height):
                    core_tiles.append(ct)

        # --- helper: distance to closest core tile ---
        def dist_to_core(p):
            best = float('inf')
            for ct in core_tiles:
                d = p.distance_squared(ct)
                if d < best:
                    best = d
            return best

        # --- 1. if any core tile is directly reachable, return it ---
        best_core_tile = None
        best_core_dist = float('inf')

        for ct in core_tiles:
            if start.distance_squared(ct) <= GameConstants.BRIDGE_TARGET_RADIUS_SQ:
                if not rc.is_in_vision(ct):
                    continue
                if rc.get_tile_env(ct) == Environment.WALL:
                    continue

                d = start.distance_squared(ct)
                if d < best_core_dist:
                    best_core_dist = d
                    best_core_tile = ct

        if best_core_tile is not None:
            return (best_core_tile, True)

        # --- 2. reuse existing bridge/conveyor if possible ---
        # best_bridge = None
        # best_bridge_dist = float('inf')

        # for dx in range(-3, 4):
        #     for dy in range(-3, 4):
        #         if dx*dx + dy*dy > GameConstants.BRIDGE_TARGET_RADIUS_SQ:
        #             continue

        #         pos = Position(start.x + dx, start.y + dy)

        #         if not is_in_map(pos, width, height):
        #             continue
        #         if not rc.is_in_vision(pos):
        #             continue

        #         building_id = rc.get_tile_building_id(pos)
        #         if building_id is None:
        #             continue
        #         if rc.get_entity_type(building_id) != EntityType.BRIDGE:
        #             continue
        #         if self.connect_current.__contains__(pos):
        #             continue

        #         d = dist_to_core(pos)
        #         if d < best_bridge_dist:
        #             best_bridge_dist = d
        #             best_bridge = pos

        # if best_bridge is not None:
        #     return (best_bridge, True)

        # --- 3. pick best new bridge position ---
        best = None
        best_dist = float('inf')
        build_finish = False

        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if dx*dx + dy*dy > GameConstants.BRIDGE_TARGET_RADIUS_SQ:
                    continue

                pos = Position(start.x + dx, start.y + dy)

                if not is_in_map(pos, width, height):
                    continue
                if not rc.is_in_vision(pos):
                    continue
                
                bldg = rc.get_tile_building_id(pos)
                if rc.get_tile_env(pos) == Environment.WALL:
                    continue
                is_to_bridge = False
                if bldg is not None:
                    t = rc.get_entity_type(bldg)
                    team = rc.get_team(bldg)
                    if team != rc.get_team() or \
                        not (t == EntityType.MARKER or t == EntityType.ROAD or t == EntityType.CONVEYOR or t == EntityType.BRIDGE):
                        continue
                    if t == EntityType.BRIDGE:
                        is_to_bridge = True

                d = dist_to_core(pos)

                if d < best_dist:
                    best_dist = d
                    best = pos
                    build_finish = is_to_bridge

        return (best if best is not None else start, build_finish)
    
    def should_connect_to_ore(self, pos: Position):
        if pos is None: return False
        
        if self.explore_blacklist.__contains__(pos): return False

        if self.sense.get_building_type(pos) == EntityType.HARVESTER:
            bldg = self.rc.get_tile_building_id(pos)
            if self.rc.get_team(bldg) == self.rc.get_team():
                return False
        
        return True
