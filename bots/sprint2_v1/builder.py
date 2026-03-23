import sys
import pathfind
import random

import sense
import visualize
from helpers import is_adjacent, is_adjacent_with_diag, cardinal_direction_to, biased_random_dir, is_in_map, guess_symmetry, get_symmetric, DIRECTIONS, CARDINAL_DIRECTIONS

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants

EXPLORE_TIMEOUT = 16
NUKE_WAIT_FOR = 500 # Wait 600 turns before starting to nuke
CORE_DANGER_RANGE = 64 # 8 Tiles away are insta nuked

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
    DEF_GOTO_ENEMY = "Go To Enemy"
    DEF_MARK_RESOURCE = "Mark Resource"
    DEF_HIJACK_RESOURCE = "Hijack Resource"
    DEF_TODO = "Todo"

class BuilderBot(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.job = BotJob.ECONOMY
        self.state_turn_counter = 0
        self.center_pos = Position(self.rc.get_map_width() // 2, self.rc.get_map_height() // 2)

        self.sense = sense.Sense(rc)
        self.pathfind_target = None
        
        self.core_pos = self.rc.get_position()
        buildings = rc.get_nearby_buildings(3)
        for b in buildings:
            if rc.get_entity_type(b) == EntityType.CORE:
                self.core_pos = rc.get_position(b)
                break
        
        if self.core_pos == self.rc.get_position():
            self.state = BotState.DEF_CORE_DEFENCE
        else:
            self.state = BotState.ECON_EXPLORE
            
        # TODO assuming rotational symmetry here, but work on changing that
        self.enemy_core_pos = get_symmetric(self.core_pos, self.rc.get_map_width(), self.rc.get_map_height(), guess_symmetry(self.rc.get_map_width(), self.rc.get_map_height()))
        
        self.explore_dir = rc.get_position().direction_to(self.center_pos)
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
                self.def_core_defence()
            case BotState.DEF_GOTO_ENEMY:
                self.def_goto_enemy()
            case BotState.DEF_MARK_RESOURCE:
                self.def_mark_resource()
            case BotState.DEF_HIJACK_RESOURCE:
                self.def_hijack_resource()
            case BotState.DEF_TODO:
                pass
        
        # pathfind.cardinal_pathfind_to(self.rc, Position(6, 7), False)

    def end_turn(self):
        # Compute symmetry if time left
        # DEBUG: sensing
        # visualize.visualize_map_minimal(self.rc, self.sense)
        print(self.state, self.pathfind_target)
        if self.pathfind_target is not None: self.rc.draw_indicator_line(self.rc.get_position(), self.pathfind_target, 10, 80, 230)
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
                if tested == 4: self.explore_blacklist.append(self.sense.nearest_ore)
                return
            
            self.state_turn_counter = 0
            self.state = BotState.ECON_TARGET
            self.explore_ore_target = self.sense.nearest_ore
            self.pathfind_target = self.sense.nearest_ore.add(best_one_off)
            return

        # if self.sense.nearest_enemy_infra is not None:
        #     # TODO Check nukability
        #     core_dist = self.sense.nearest_enemy_infra.distance_squared(self.core_pos)
        #     if self.rc.get_current_round() > NUKE_WAIT_FOR or core_dist < CORE_DANGER_RANGE:
        #         self.state_turn_counter = 0
        #         self.state = BotState.ECON_NUKE
        #         self.pathfind_target = self.sense.nearest_enemy_infra

        # Actual Movement
        self.explore_timeout -= 1
        if self.explore_timeout == 0:
            self.explore_timeout = EXPLORE_TIMEOUT
            self.explore_dir = biased_random_dir(self.rc)
            
        next_pos = self.rc.get_position().add(self.explore_dir)
        if not is_in_map(next_pos, self.rc.get_map_width(), self.rc.get_map_height()):
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

        # splitter_edges = [
        #     (self.core_pos.add(Direction.EAST) .add(Direction.NORTHEAST), Direction.WEST),
        #     (self.core_pos.add(Direction.EAST) .add(Direction.SOUTHEAST), Direction.WEST),
        #     (self.core_pos.add(Direction.WEST) .add(Direction.NORTHWEST), Direction.EAST),
        #     (self.core_pos.add(Direction.WEST) .add(Direction.SOUTHWEST), Direction.EAST),
        #     (self.core_pos.add(Direction.NORTH).add(Direction.NORTHEAST), Direction.SOUTH),
        #     (self.core_pos.add(Direction.NORTH).add(Direction.NORTHWEST), Direction.SOUTH),
        #     (self.core_pos.add(Direction.SOUTH).add(Direction.SOUTHEAST), Direction.NORTH),
        #     (self.core_pos.add(Direction.SOUTH).add(Direction.SOUTHWEST), Direction.NORTH),
        # ]
    def def_core_defence(self):
        
        current_pos = self.rc.get_position()
        # print(self.get_defence_plan())
        
        for dx, dy, desired_type, dir in self.get_defence_plan():
            target = Position(self.core_pos.x + dx, self.core_pos.y + dy)

            if not is_in_map(target, self.rc.get_map_width(), self.rc.get_map_height()): continue
            if not self.rc.is_in_vision(target): continue
            bldg_id = self.rc.get_tile_building_id(target)

            valid = (
                bldg_id is not None and \
                self.rc.get_team(bldg_id) == self.rc.get_team() and \
                self.rc.get_entity_type(bldg_id) == desired_type
            )
            if valid: continue
            self.rc.draw_indicator_dot(target, 255, 0, 0)
            
            if not self.rc.is_tile_empty(target):
                if self.rc.can_destroy(target):
                    self.rc.destroy(target)
            
            if desired_type == EntityType.LAUNCHER:
                # print('launcher????', file=sys.stderr)
                if self.rc.can_build_launcher(target):
                    self.rc.build_launcher(target)
                    return
            elif desired_type == EntityType.SPLITTER:
                # print('splitter????', file=sys.stderr)
                if self.rc.can_build_splitter(target, dir):
                    self.rc.build_splitter(target, dir)
            elif desired_type == EntityType.FOUNDRY:
                # print('splitter????', file=sys.stderr)
                if self.rc.can_build_foundry(target):
                    self.rc.build_foundry(target)

            if not is_adjacent_with_diag(current_pos, target):
                pathfind.fast_pathfind_to(self.rc, target)
                return

        # if self.rc.get_current_round() > 200:
        #     self.state_turn_counter = 0
        #     self.state = BotState.DEF_GOTO_ENEMY
        #     self.pathfind_target = self.enemy_core_pos
        # else:
        self.state_turn_counter = 0
        self.state = BotState.ECON_EXPLORE
        self.explore_dir = self.core_pos.direction_to(self.rc.get_position())
        self.explore_timeout = EXPLORE_TIMEOUT
        self.explore_ore_target = None


    def get_defence_plan(self):
        plan = []
        (ti, ax) = self.rc.get_global_resources()
        if self.rc.get_current_round() > 30 and ti > 500:
            plan.extend([
                # (2, 2, EntityType.LAUNCHER, Direction.CENTRE),
                # (-2, 2, EntityType.LAUNCHER, Direction.CENTRE),
                # (2, -2, EntityType.LAUNCHER, Direction.CENTRE),
                # (-2, -2, EntityType.LAUNCHER, Direction.CENTRE),
                ( 1,  2, EntityType.SPLITTER, Direction.NORTH),
                (-1,  2, EntityType.SPLITTER, Direction.NORTH),
                ( 0,  2, EntityType.FOUNDRY, Direction.CENTRE)
                # ( 1, -2, EntityType.SPLITTER, Direction.SOUTH),
                # (-1, -2, EntityType.SPLITTER, Direction.SOUTH),
            ])
        return plan

    def def_goto_enemy(self):
        pathfind.fast_pathfind_to(self.rc, self.pathfind_target)
        if self.rc.is_in_vision(self.enemy_core_pos):
            bldg = self.rc.get_tile_building_id(self.enemy_core_pos)
            entt = self.rc.get_entity_type(bldg)
            if entt == EntityType.CORE:
                (pos, replace) = self.compute_best_hijack_target()
                if pos is not None:
                    self.state_turn_counter = 0
                    if replace:
                        self.state = BotState.DEF_HIJACK_RESOURCE
                    else:
                        self.state = BotState.DEF_MARK_RESOURCE
                    self.pathfind_target = pos
            else:
                print(self.enemy_core_pos, 'is not the enemy core')
                self.state_turn_counter = 0
                self.state = BotState.ECON_EXPLORE
                self.explore_dir = self.core_pos.direction_to(self.rc.get_position())
                self.explore_timeout = EXPLORE_TIMEOUT
                self.explore_ore_target = None
                return



    def def_mark_resource(self):
        entities = self.rc.get_nearby_entities()
        entity_neighbour_exists = None
        already_occupied = False
        for e in entities:
            if e == self.rc.get_id(): continue
            entt = self.rc.get_entity_type(e)
            if entt == EntityType.BUILDER_BOT and self.rc.get_team(e) == self.rc.get_team():
                if self.rc.get_position(e) == self.pathfind_target:
                    already_occupied = True
                    break
                if is_adjacent_with_diag(self.rc.get_position(), self.rc.get_position(e)):
                    entity_neighbour_exists = e
                    break
        
        if already_occupied:
            self.state_turn_counter = 0
            self.state = BotState.DEF_GOTO_ENEMY
            self.pathfind_target = self.enemy_core_pos
        
        if pathfind.fast_pathfind_to(self.rc, self.pathfind_target):
            if entity_neighbour_exists is not None:
                print(self.rc.get_id(), 'destroying self because of', e, file=sys.stderr)
                self.rc.self_destruct()

    def def_hijack_resource(self):
        if not is_adjacent_with_diag(self.rc.get_position(), self.pathfind_target):
            pathfind.fast_pathfind_to(self.rc, self.pathfind_target)
            print(self.rc.get_current_round(), 'moving=', self.rc.get_id(), sys.stderr)
        else:
            print(self.rc.get_current_round(), 'test build=', self.rc.get_id(), sys.stderr)
            d = self.pathfind_target.direction_to(self.enemy_core_pos)
            if self.rc.can_build_sentinel(self.pathfind_target, d):
                self.rc.build_sentinel(self.pathfind_target, d)
                self.state_turn_counter = 0
                self.state = BotState.DEF_GOTO_ENEMY
                self.pathfind_target = self.enemy_core_pos
                

    def compute_best_hijack_target(self) -> (Position, bool):
        best_priority = -100000
        entities = self.rc.get_nearby_entities()
        answer: Position = None

        valid_tiles = []
        for e in entities:
            if e == self.rc.get_id(): continue
                
            entt = self.rc.get_entity_type(e)
            d_to_core = self.rc.get_position(e).distance_squared(self.enemy_core_pos)
            
            if d_to_core > 16:
                continue

            if entt == EntityType.CONVEYOR or entt == EntityType.BRIDGE:
                p = self.rc.get_position(e)
                valid_tiles.append(p)
                if best_priority < 10:
                    answer = self.rc.get_position(e)
                    best_priority = 10
            elif entt == EntityType.HARVESTER:
                found_dir = None
                best_dist = 1000000
                
                for d in CARDINAL_DIRECTIONS:
                    p = self.rc.get_position(e).add(d)
                    valid_tiles.append(p)
                    if not self.rc.is_in_vision(p): continue
                    dist = p.distance_squared(self.enemy_core_pos)
                    if not (self.rc.is_tile_empty(p) or self.rc.is_tile_passable(p)): continue
                    
                    if dist < best_dist:
                        best_dist = dist
                        found_dir = d
                
                if found_dir is not None and best_priority < 20:
                    answer = self.rc.get_position(e)
                    best_priority = 20
        
        for e in entities:
            if e == self.rc.get_id(): continue
                
            entt = self.rc.get_entity_type(e)
            p = self.rc.get_position(e)

            if entt == EntityType.BUILDER_BOT and self.rc.get_team(e) == self.rc.get_team(): print(valid_tiles)
            if entt == EntityType.BUILDER_BOT and self.rc.get_team(e) == self.rc.get_team() and p in valid_tiles:
                answer = self.rc.get_position(e)
                print('found bot waiting to die ', e, file=sys.stderr)
                return (answer, True)

        return (answer, False)

    
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
        plan = self.get_defence_plan()
        for dx, dy, entity_type, dir in plan:
            if entity_type == EntityType.SPLITTER:
                pos = Position(core.x + dx, core.y + dy)
                if is_in_map(pos, width, height):
                    core_tiles.append(pos)

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
        best_bridge = None
        best_bridge_dist = float('inf')

        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if dx*dx + dy*dy > GameConstants.BRIDGE_TARGET_RADIUS_SQ:
                    continue

                pos = Position(start.x + dx, start.y + dy)

                if not is_in_map(pos, width, height):
                    continue
                if not rc.is_in_vision(pos):
                    continue

                building_id = rc.get_tile_building_id(pos)
                if building_id is None:
                    continue
                if rc.get_entity_type(building_id) != EntityType.BRIDGE:
                    continue
                if self.connect_current.__contains__(pos):
                    continue

                d = dist_to_core(pos)
                if d < best_bridge_dist:
                    best_bridge_dist = d
                    best_bridge = pos

        if best_bridge is not None:
            return (best_bridge, True)

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
                        not (t == EntityType.MARKER or t == EntityType.ROAD or t == EntityType.SPLITTER or t == EntityType.CONVEYOR or t == EntityType.BRIDGE):
                        continue
                    if t == EntityType.BRIDGE or t == EntityType.SPLITTER:
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
            else:
                has_free_side = False
                for d in CARDINAL_DIRECTIONS:
                    p = pos.add(d)
                    if not self.rc.is_in_vision(p): continue
                    if self.rc.is_tile_empty(p) or \
                        (self.sense.is_friendly_building(p) and self.sense.get_building_type(p) == EntityType.ROAD):
                        has_free_side = True
                        break
                
                if has_free_side: print('siphoning resources from ', pos, file=sys.stderr)
                return has_free_side
        
        return True
