import sys
import pathfind
import random

from helpers import get_best_empty_adj, get_empty_adj, is_friendly_transport, is_entt_pathable, is_pos_editable, is_pos_pathable, get_building_type, is_adjacent, is_adjacent_with_diag, cardinal_direction_to, biased_random_dir, is_in_map, guess_symmetry, get_symmetric, DIRECTIONS, CARDINAL_DIRECTIONS

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants, ResourceType

BOT_EXPLORE_TIMEOUT = 8

class BotState(Enum):
    ECON_EXPLORE = "Explore"
    ECON_TARGET  = "Target"
    ECON_CONNECT = "Connect"
    ECON_NUKE    = "Nuke"

class BuilderBot(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        
        self.core_pos = self.rc.get_position()
        buildings = rc.get_nearby_buildings(3)
        for b in buildings:
            if rc.get_entity_type(b) == EntityType.CORE:
                self.core_pos = rc.get_position(b)
                break
        self.map_center_pos = Position(self.rc.get_map_width() // 2, self.rc.get_map_height() // 2)

        self.switch_state(BotState.ECON_EXPLORE)
        self.econ_explore_dir = rc.get_position().direction_to(self.map_center_pos)

    def reset_state_variables(self):
        self.pathfind_target: Position = None
        self.econ_explore_dir: Direction = Direction.CENTRE
        self.econ_explore_timeout: int = BOT_EXPLORE_TIMEOUT
        self.econ_target_ore: Position = None
        self.econ_target_is_ax: bool = False
        self.connect_current_target: Position = None
        self.connect_current_run: list[Position] = []
        self.connect_current_should_bridge: bool = True
        
        # Some states want sub-states
        self.state_custom_sub_state: int = 0
    
    def switch_state(self, state: BotState):
        self.state = state
        self.state_turn_counter = 0
        self.reset_state_variables()

    def start_turn(self):
        pass
    
    def turn(self):
        match self.state:
            case BotState.ECON_EXPLORE:
                self.econ_explore()
            case BotState.ECON_TARGET:
                self.econ_target()
            case BotState.ECON_CONNECT:
                self.econ_connect()
            case BotState.ECON_NUKE:
                self.econ_nuke()
    
    def econ_explore(self):
        # Defence Plan Guarantee
        plan = self.get_defence_plan()
        if not self.verify_defences():
            return

        # Possibly Find and Target Ore TITANIUM
        for pos in self.rc.get_nearby_tiles():
            env = self.rc.get_tile_env(pos)
            if env == Environment.ORE_TITANIUM or env == Environment.ORE_AXIONITE:
                (should_connect, dir) = self.should_connect_to_ore(pos, env == Environment.ORE_AXIONITE)
                if should_connect:
                    self.switch_state(BotState.ECON_TARGET)
                    self.econ_target_ore = pos
                    self.pathfind_target = pos.add(dir)
                    self.econ_target_is_ax = env == Environment.ORE_AXIONITE

        # Timeout direction switch
        self.econ_explore_timeout -= 1
        if self.econ_explore_timeout == 0:
            self.econ_explore_timeout = BOT_EXPLORE_TIMEOUT
            self.econ_explore_dir = biased_random_dir(self.rc)

        # Actual Move
        next_pos = self.rc.get_position().add(self.econ_explore_dir)
        if not is_in_map(next_pos, self.rc.get_map_width(), self.rc.get_map_height()):
            self.econ_explore_dir = biased_random_dir(self.rc)
            return

        if self.rc.can_move(self.econ_explore_dir):
            self.rc.move(self.econ_explore_dir)
        elif self.rc.is_tile_empty(next_pos):
            if self.rc.can_build_road(next_pos):
                self.rc.build_road(next_pos)
                if self.rc.can_move(self.econ_explore_dir):
                    self.rc.move(self.econ_explore_dir)
        else:
            self.econ_explore_dir = biased_random_dir(self.rc)
        

    def econ_target(self):
        (should_connect, dir) = self.should_connect_to_ore(self.econ_target_ore, self.econ_target_is_ax)
        if not should_connect:
            self.switch_state(BotState.ECON_EXPLORE)
            self.econ_explore_dir = biased_random_dir(self.rc)
            return

        if is_adjacent(self.rc.get_position(), self.econ_target_ore):
            if not self.rc.is_tile_empty(self.econ_target_ore) and get_building_type(self.rc, self.econ_target_ore) != EntityType.HARVESTER:
                if self.rc.can_destroy(self.econ_target_ore):
                    self.rc.destroy(self.econ_target_ore)
            if self.rc.can_build_harvester(self.econ_target_ore):
                self.rc.build_harvester(self.econ_target_ore)

            bldg = self.rc.get_tile_building_id(self.econ_target_ore)
            if bldg is not None and self.rc.get_entity_type(bldg) == EntityType.HARVESTER:
                is_ax = self.econ_target_is_ax
                self.switch_state(BotState.ECON_CONNECT)
                self.pathfind_target = self.core_pos
                self.econ_target_is_ax = is_ax
        else:
            pathfind.fast_pathfind_to(self.rc, self.pathfind_target)

    def econ_connect(self):
        # if self.state_custom_sub_state == 0:
        #     new_conveyor_pos = self.rc.get_position()
        #     if self.rc.can_destroy(new_conveyor_pos):
        #         self.rc.destroy(new_conveyor_pos)
        #     the_dir = cardinal_direction_to(new_conveyor_pos, self.core_pos)
        #     if self.rc.can_build_conveyor(new_conveyor_pos, the_dir):
        #         self.rc.build_conveyor(new_conveyor_pos, the_dir)
        #         self.state_custom_sub_state = 1

        # if pathfind.cardinal_pathfind_to(self.rc, self.pathfind_target, True):
        #     
        #

        
        if self.connect_current_target is not None and self.rc.get_position() != self.connect_current_target:
            if self.connect_current_should_bridge:
                pathfind.fast_pathfind_to(self.rc, self.connect_current_target)
            else:
                pathfind.cardinal_pathfind_to(self.rc, self.connect_current_target, True)
                self.connect_current_run.append(self.rc.get_position())
            
        else:
            bldg = self.rc.get_tile_building_id(self.rc.get_position())
            allied = self.rc.get_team(bldg) == self.rc.get_team()
            if allied and (get_building_type(self.rc, self.rc.get_position()) == EntityType.ROAD or get_building_type(self.rc, self.rc.get_position()) == EntityType.CONVEYOR):
                self.rc.destroy(self.rc.get_position())
            elif not allied:
                if self.rc.can_fire(self.rc.get_position()):
                    self.rc.fire(self.rc.get_position())
                
            (best_target, final_one, is_to_core) = self.compute_best_bridge_target(self.econ_target_is_ax)
            self.connect_current_should_bridge = (not pathfind.is_tile_within_n_cardinal_steps(self.rc, self.rc.get_position(), best_target, 3) or is_to_core or final_one)

            if self.connect_current_should_bridge:
                if self.rc.can_build_bridge(self.rc.get_position(), best_target):
                    self.rc.build_bridge(self.rc.get_position(), best_target)
                    self.connect_current_run.append(self.rc.get_position())
                else:
                    # print('best_target=',best_target, file=sys.stderr
                    return
            
            self.connect_current_target = best_target

            if final_one:
                print('final one apparently')
                self.switch_state(BotState.ECON_EXPLORE)
                self.econ_explore_dir = biased_random_dir(self.rc)
                return


    def econ_nuke(self):
        if pathfind.fast_pathfind_to(self.rc, self.pathfind_target):
            self.rc.self_destruct()

    def end_turn(self):
        if self.pathfind_target is not None: self.rc.draw_indicator_line(self.rc.get_position(), self.pathfind_target, 220, 50, 50)
        print(self.state)
        pass


    # CORE DEFENCE PLAN
    
    def get_defence_plan(self):
        plan = [
            # (2, 2, EntityType.LAUNCHER, Direction.CENTRE),
            # (-2, 2, EntityType.LAUNCHER, Direction.CENTRE),
            # (2, -2, EntityType.LAUNCHER, Direction.CENTRE),
            # (-2, -2, EntityType.LAUNCHER, Direction.CENTRE),
            # ( 1,  2, EntityType.SPLITTER, Direction.NORTH),
            (-1,  2, EntityType.SPLITTER, Direction.NORTH),
            # ( 0,  2, EntityType.FOUNDRY, Direction.CENTRE)
            # ( 1, -2, EntityType.SPLITTER, Direction.SOUTH),
            # (-1, -2, EntityType.SPLITTER, Direction.SOUTH),
        ]
        
        (ti, ax) = self.rc.get_global_resources()
        if self.rc.get_current_round() > 30 and ti > 500:
            plan.extend([
                # (2, 2, EntityType.LAUNCHER, Direction.CENTRE),
                # (-2, 2, EntityType.LAUNCHER, Direction.CENTRE),
                # (2, -2, EntityType.LAUNCHER, Direction.CENTRE),
                # (-2, -2, EntityType.LAUNCHER, Direction.CENTRE),
                # ( 1,  2, EntityType.SPLITTER, Direction.NORTH),
                # (-1,  2, EntityType.SPLITTER, Direction.NORTH),
                ( 0,  2, EntityType.FOUNDRY, Direction.CENTRE)
                # ( 1, -2, EntityType.SPLITTER, Direction.SOUTH),
                # (-1, -2, EntityType.SPLITTER, Direction.SOUTH),
            ])

        return plan

    def verify_defences(self) -> bool:
        plan = self.get_defence_plan()
        for dx, dy, desired_type, dir in plan:
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
            
            should_destroy_enemy_stuff = self.rc.get_team(bldg_id) != self.rc.get_team() and is_pos_pathable(self.rc, target)
            if (should_destroy_enemy_stuff and self.rc.get_position() != target) or (not is_adjacent_with_diag(self.rc.get_position(), target)):
                pathfind.fast_pathfind_to(self.rc, target)
                return False
            
            if not self.rc.is_tile_empty(target):
                if self.rc.can_destroy(target):
                    self.rc.destroy(target)
                elif self.rc.can_fire(target):
                    self.rc.fire(target)
            
            if self.rc.get_position() == target and self.rc.is_tile_empty(target):
                move_dir = get_empty_adj(self.rc, target)
                new_pos = target.add(move_dir)
                pathfind.fast_pathfind_to(self.rc, new_pos)
            
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
            
        return True

    # Some Helpers

    def compute_best_bridge_target(self, connecting_ax: bool) -> (Position, bool, bool):
        rc = self.rc
        start = rc.get_position()
        core = self.core_pos
        self_to_core_dist = start.distance_squared(core)

        width, height = rc.get_map_width(), rc.get_map_height()

        # --- collect core 3x3 tiles --- TODO probably cache
        core_tiles = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                ct = Position(core.x + dx, core.y + dy)
                if is_in_map(ct, width, height):
                    core_tiles.append(ct)
        
        core_splitter_tiles = []
        core_foundry_tiles = []
        plan = self.get_defence_plan()
        for dx, dy, entity_type, dir in plan:
            if entity_type == EntityType.SPLITTER:
                pos = Position(core.x + dx, core.y + dy)
                if is_in_map(pos, width, height):
                    core_splitter_tiles.append(pos)
            elif entity_type == EntityType.FOUNDRY:
                pos = Position(core.x + dx, core.y + dy)
                if is_in_map(pos, width, height):
                    core_foundry_tiles.append(pos)

        # --- helper: distance to closest core tile ---
        def dist_to_core(p):
            best = float('inf')
            if connecting_ax:
                for ct in core_foundry_tiles:
                    d = p.distance_squared(ct)
                    if d < best:
                        best = d
            else:
                for ct in core_tiles:
                    d = p.distance_squared(ct)
                    if d < best:
                        best = d
                for ct in core_splitter_tiles:
                    d = p.distance_squared(ct)
                    if d < best:
                        best = d

            return best

        # --- 1. if any core tile is directly reachable, return it ---
        best_core_tile = None
        best_core_dist = float('inf')

        if connecting_ax:
            for ct in core_foundry_tiles:
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
                print('track0')
                return (best_core_tile, True, True)
        else:
            for ct in core_splitter_tiles:
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
                print('track1')
                return (best_core_tile, True, True)

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
                print('track2')
                return (best_core_tile, True, True)

        # --- 2. reuse existing bridge/conveyor/splitter if possible ---
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
                if building_id is None: continue
                if rc.get_team(building_id) != rc.get_team(): continue

                if rc.get_entity_type(building_id) != EntityType.BRIDGE and rc.get_entity_type(building_id) != EntityType.CONVEYOR  and rc.get_entity_type(building_id) != EntityType.SPLITTER:
                    continue
                if self.connect_current_run.__contains__(pos):
                    continue
                
                testing_resource = ResourceType.RAW_AXIONITE if connecting_ax else ResourceType.TITANIUM
                if rc.get_stored_resource(building_id) != testing_resource:
                    continue

                d = dist_to_core(pos)
                if d < best_bridge_dist and self_to_core_dist > d:
                    best_bridge_dist = d
                    best_bridge = pos

        if best_bridge is not None:
            print('track3', best_bridge)
            return (best_bridge, True, False)

        # --- 3. pick best new bridge position ---
        best = None
        best_dist = float('inf')

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
                if bldg is not None:
                    continue

                d = dist_to_core(pos)
                
                if d < best_dist:
                    best_dist = d
                    best = pos
                    # build_finish = is_to_bridge

        print('track4')
        return (best if best is not None else start, False, False)
    

    def should_connect_to_ore(self, pos: Position, is_ax: bool) -> (bool, Direction):
        if pos is None: return (False, Direction.CENTRE)
        
        (ti, ax) = self.rc.get_global_resources()
        if is_ax and ti < 300: return (False, Direction.CENTRE)
        if not self.rc.is_in_vision(pos): return (False, Direction.CENTRE)
        
        bldg = self.rc.get_tile_building_id(pos)
        has_free_side = False
        already_siphoned = False
        # not_enough_info = False
        
        # if bldg is None or (self.rc.get_entity_type(bldg) == EntityType.HARVESTER):
        for d in CARDINAL_DIRECTIONS:
            p = pos.add(d)
            if not is_in_map(p, self.rc.get_map_width(), self.rc.get_map_height()): continue
            if not self.rc.is_in_vision(p): return (False, Direction.CENTRE) # not enough info
            bb = self.rc.get_tile_builder_bot_id(p)
            if bb is not None and self.rc.get_id() != bb:
                if self.rc.get_team(bb) == self.rc.get_team():
                    already_siphoned = True
                    break
            if is_friendly_transport(self.rc, p):
                already_siphoned = True
                break
            if self.rc.is_tile_empty(p) or is_pos_editable(self.rc, p):
                has_free_side = True
        
        return (has_free_side and not already_siphoned, get_best_empty_adj(self.rc, pos, self.core_pos))
        # return (False, Direction.CENTRE)
