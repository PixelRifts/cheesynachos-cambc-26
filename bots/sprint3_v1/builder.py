import sys
import sense
import pathfind
import random

from bot import Bot
from helpers import *
from procedure import *

from enum import Enum
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants, ResourceType

BOT_EXPLORE_TIMEOUT = 12
AXIONITE_ENABLE_ROUND = 200
CORE_DANGER = 20

class BotState(Enum):
    ECON_EXPLORE = "Explore"
    ECON_TARGET  = "Target"
    ECON_CONNECT = "Connect"
    ECON_NUKE    = "Nuke"

    DEFENCE_HEAL = "Heal"

    ATTACK_GOTO      = "Goto"
    ATTACK_BLOCK_ORE = "Block"
    ATTACK_HIJACK    = "Hijack"

class BuilderBot(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)

        self.sense = sense.Sense(self.rc)
        
        self.core_pos = self.rc.get_position()
        for b in rc.get_nearby_buildings(3):
            if rc.get_entity_type(b) == EntityType.CORE:
                self.core_pos = rc.get_position(b)
                break
        self.map_center_pos = Position(self.rc.get_map_width() // 2, self.rc.get_map_height() // 2)
        self.enemy_core_pos = get_symmetric(self.core_pos, self.sense.map_width, self.sense.map_height, self.sense.symmetries_possible[0])

        self.switch_state(BotState.ECON_EXPLORE)


    def reset_state_variables(self):
        self.pathfind_target: Position = None
        
        self.econ_explore_dir: Direction = Direction.NORTH
        self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
        self.econ_explore_timeout: int = BOT_EXPLORE_TIMEOUT
        self.econ_target_ore: Position = None
        self.econ_target_is_ax: bool = False
        
    def switch_state(self, state: BotState):
        self.state = state
        self.state_turn_counter = 0
        self.reset_state_variables()

    def start_turn(self):
        self.sense.update()

        self.enemy_core_pos = self.sense.enemy_core_found if self.sense.enemy_core_found is not None else \
            get_symmetric(self.core_pos, self.rc.get_map_width(), self.rc.get_map_height(), self.sense.symmetries_possible[0])
        
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
            
            case BotState.DEFENCE_HEALER:
                self.defence_healer()

            case BotState.ATTACK_GOTO:
                self.attack_goto()
            case BotState.ATTACK_BLOCK_ORE:
                self.attack_block_ore()
            case BotState.ATTACK_HIJACK:
                self.attack_hijack()
    
    def end_turn(self):
        # self.sense.visualize()
        pass
        
    ### ========================
    ###     State Functions 
    ### ========================

    def econ_explore(self):
        my_pos = self.rc.get_position()

        # Pick nearest Titanium Ore to target
        closest_ore = None
        closest_ore_dir = Direction.CENTRE
        closest_ore_is_ax = False
        closest_ore_dist = 10000000
        for o in self.sense.env_index[sense._ENVIRONMENT_TO_VALUE[Environment.ORE_TITANIUM]]:
            (should_connect, dir) = self.should_connect_to_ore(o, False)
            if should_connect:
                dist = o.distance_squared(my_pos)
                if dist < closest_ore_dist:
                    closest_ore_dist = dist
                    closest_ore = o
                    closest_ore_is_ax = False
                    closest_ore_dir = dir
        
        if closest_ore is not None:
            self.switch_state(BotState.ECON_TARGET)
            self.econ_target_ore = closest_ore
            self.pathfind_target = closest_ore.add(closest_ore_dir)
            self.econ_target_is_ax = closest_ore_is_ax
            return

        # Timeout to switch direction after BOT_EXPLORE_TIMEOUT time
        self.econ_explore_timeout -= 1
        if self.econ_explore_timeout == 0:
            self.econ_explore_timeout = BOT_EXPLORE_TIMEOUT
            self.econ_explore_dir = biased_random_dir(self.rc)
            self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)

        # Actually Pathfind
        if pathfind.fast_pathfind_to(self.rc, self.pathfind_target):
            self.econ_explore_timeout = BOT_EXPLORE_TIMEOUT
            self.econ_explore_dir = biased_random_dir(self.rc)
            self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)

    def econ_target(self):
        # Make sure there aren't new developments concerning the ore
        should_connect, _ = self.should_connect_to_ore(self.econ_target_ore, self.econ_target_is_ax)
        if not should_connect:
            self.switch_state(BotState.ECON_EXPLORE)
            self.econ_explore_dir = biased_random_dir(self.rc)
            self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
            return
        
        if not self.rc.is_in_vision(self.econ_target_ore):
            pathfind.fast_pathfind_to(self.rc, self.pathfind_target)
            return

        valid_count = 0
        for d in CARDINAL_DIRECTIONS:
            adj = self.econ_target_ore.add(d)

            if adj == self.pathfind_target: continue
            if not is_in_map(adj, self.rc.get_map_width(), self.rc.get_map_height()): continue
            if not self.rc.is_in_vision(adj): continue

            entt = self.sense.get_entity(adj)
            allied = self.sense.is_allied(adj)
            env = self.sense.get_env(adj)

            if env == Environment.WALL or \
                (entt in ENTITY_VALID_BLOCKAGE_ANY) or \
                (allied and entt in ENTITY_VALID_BLOCKAGE_FRIENDLY):
                valid_count += 1
            else:
                if try_destroy(self.rc, self.sense, self.econ_target_ore, adj):
                    if self.rc.can_build_barrier(adj):
                        self.rc.build_barrier(adj)
                        valid_count += 1
                else:
                    return

    def econ_connect(self):
        pass

    def econ_nuke(self):
        pass

    def defence_healer(self):
        pass

    def attack_goto(self):
        pass

    def attack_block_ore(self):
        pass

    def attack_hijack(self):
        pass


    # Helpers
    def should_connect_to_ore(self, pos: Position, is_ax: bool) -> (bool, Direction):
        if pos is None: return (False, Direction.CENTRE)
        
        (ti, ax) = self.rc.get_global_resources()
        if is_ax:
            if ti < 300 or self.rc.get_current_round() < AXIONITE_ENABLE_ROUND or not sense.ti_ever_increased():
                return (False, Direction.CENTRE)
        if not self.rc.is_in_vision(pos): return (False, Direction.CENTRE)
        
        if is_friendly_transport(self.rc, pos): return (False, Direction.CENTRE)
        
        has_free_side = False
        already_siphoned = False
        bot_marked = False
        not_enough_info = False
        harvester_placable = is_pos_editable(self.rc, pos)
        has_harvester = self.sense.get_entity(pos) == EntityType.HARVESTER
        
        # if bldg is None or (self.rc.get_entity_type(bldg) == EntityType.HARVESTER):
        for d in CARDINAL_DIRECTIONS:
            p = pos.add(d)
            if not is_in_map(p, self.rc.get_map_width(), self.rc.get_map_height()): continue
            if not self.rc.is_in_vision(p):
                not_enough_info = True
                continue

            bb = self.rc.get_tile_builder_bot_id(p)
            if bb is not None and self.rc.get_id() != bb:
                if self.rc.get_team(bb) == self.rc.get_team():
                    bot_marked = True

            if is_friendly_transport(self.rc, p):
                already_siphoned = True
                
            if is_pos_editable(self.rc, p):
                has_free_side = True
        
        if bot_marked: return (False, Direction.CENTRE)
        if has_harvester and already_siphoned: return (False, Direction.CENTRE)
        if not has_harvester and already_siphoned: return (harvester_placable, get_best_empty_adj(self.rc, pos, self.core_pos))
        if has_harvester and not already_siphoned: return (not not_enough_info, get_best_empty_adj(self.rc, pos, self.core_pos))
        if not has_harvester and not already_siphoned and harvester_placable: return (not not_enough_info, get_best_empty_adj(self.rc, pos, self.core_pos))

        return (False, Direction.CENTRE)
