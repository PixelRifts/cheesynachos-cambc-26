import sys
import sense
import pathfind
import random
import heapq

from bot import Bot
from helpers import *
from procedure import *

from enum import Enum
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants, ResourceType

BOT_EXPLORE_TIMEOUT = 12
BOT_TARGET_STUCK_TIMEOUT = 80
AXIONITE_ENABLE_ROUND = 200
CORE_DANGER = 20
BRIDGE_USAGE_CUTOFF = 5

class BotJob(Enum):
    ECON = "Econ"
    RUSH = "Rush"
    HEAL = "Heal"

class BotState(Enum):
    ECON_EXPLORE = "Explore"
    ECON_TARGET  = "Target"
    ECON_CONNECT = "Connect"
    ECON_NUKE    = "Nuke"

    CORE_HEALER = "Heal"

    ATTACK_GOTO      = "Goto"
    ATTACK_BLOCK_ORE = "Block"
    ATTACK_HIJACK    = "Hijack"

    RECOVER_GOTO_CORE = "Core"

class BuilderBot(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)

        self.sense = sense.Sense(self.rc)
        
        self.core_pos = self.rc.get_position()
        for b in rc.get_nearby_buildings(3):
            if rc.get_entity_type(b) == EntityType.CORE:
                self.core_pos = rc.get_position(b)
                break
        self.core_tiles = [ self.core_pos.add(d) for d in Direction ]
        print(self.core_tiles)
        self.map_center_pos = Position(self.rc.get_map_width() // 2, self.rc.get_map_height() // 2)
        self.enemy_core_pos = get_symmetric(self.core_pos, self.sense.map_width, self.sense.map_height, self.sense.symmetries_possible[0])
        self.rush_spawn_pos = self.core_pos.add(self.core_pos.direction_to(self.map_center_pos))

        match self.rc.get_position():
            case self.core_pos: self.job = BotJob.HEAL
            case self.rush_spawn_pos: self.job = BotJob.RUSH
            case _: self.job = BotJob.ECON
        match self.job:
            case BotJob.HEAL: self.switch_state(BotState.CORE_HEALER)
            case BotJob.ECON: self.switch_state(BotState.ECON_EXPLORE)
            case BotJob.RUSH: self.switch_state(BotState.ATTACK_GOTO)
        self.stuck_counter = 0
        self.stuck_pos = self.rc.get_position()


    def reset_state_variables(self):
        self.pathfind_target: Position = None
        
        # ECON_EXPLORE
        self.econ_explore_dir: Direction = biased_random_dir(self.rc)
        self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
        self.econ_explore_timeout: int = BOT_EXPLORE_TIMEOUT
        
        # ECON_TARGET
        self.econ_target_ore: Position = None
        self.econ_target_is_ax: bool = False
        
        # ECON_CONNECT
        self.econ_connect_final_target: Position = None
        self.econ_connect_current_target: Position = None
        self.econ_connect_current_is_bridge: bool = False
        self.econ_connect_current_is_final: bool = False
        self.econ_connect_saved_target: Position = None
        self.econ_connect_protect_target: Position = None
        self.econ_connect_saved_is_bridge: bool = False
        self.econ_connect_saved_is_final: bool = False
        self.econ_connect_launcher_count: int = 0
        self.econ_connect_current_run: list[Position] = []

        # HEAL
        self.core_heal_target: Position = None

        # ATTACK
        self.attack_target: Position = None

    def switch_state(self, state: BotState):
        self.state = state
        self.state_turn_counter = 0
        self.reset_state_variables()

    def start_turn(self):
        self.sense.update()

        self.enemy_core_pos = self.sense.enemy_core_found if self.sense.enemy_core_found is not None else \
            get_symmetric(self.core_pos, self.rc.get_map_width(), self.rc.get_map_height(), self.sense.symmetries_possible[0])
        
    def turn(self):
        if self.sense.nearest_to_heal is not None and self.state != BotState.ECON_CONNECT:
            self.meta_nearest_heal()

        match self.state:
            case BotState.ECON_EXPLORE:
                self.econ_explore()
            case BotState.ECON_TARGET:
                self.econ_target()
                if self.econ_target_ore is not None:
                    self.rc.draw_indicator_dot(self.econ_target_ore, 255, 0, 255)
                    self.rc.draw_indicator_dot(self.pathfind_target, 255, 255, 255)
            case BotState.ECON_CONNECT:
                self.econ_connect()
            case BotState.ECON_NUKE:
                self.econ_nuke()
            
            case BotState.CORE_HEALER:
                self.core_healer()

            case BotState.ATTACK_GOTO:
                self.attack_goto()
            case BotState.ATTACK_BLOCK_ORE:
                self.attack_block_ore()
            case BotState.ATTACK_HIJACK:
                self.attack_hijack()

            case BotState.RECOVER_GOTO_CORE:
                self.recover_goto_core()
    
    def end_turn(self):
        # self.sense.visualize()
        print(self.state)
        pass
        
    ### ========================
    ###     State Functions 
    ### ========================

    def meta_nearest_heal(self):
        if self.rc.get_hp() < self.rc.get_max_hp():
            if self.rc.can_heal(self.rc.get_position()):
                self.rc.heal(self.rc.get_position())
            return
        if self.rc.get_position().distance_squared(self.sense.nearest_to_heal) > GameConstants.ACTION_RADIUS_SQ:
            pathfind.fast_pathfind_to(self.rc, self.sense, self.sense.nearest_to_heal)
        if self.rc.can_heal(self.sense.nearest_to_heal):
            self.rc.heal(self.sense.nearest_to_heal)

    def econ_explore(self):
        my_pos = self.rc.get_position()

        # Pick nearest Titanium Ore to target
        closest_ore = None
        closest_ore_dir = Direction.CENTRE
        closest_ore_is_ax = False
        closest_ore_dist = 10000000
        for o in self.sense.env_index[sense.ENVIRONMENT_TO_VALUE[Environment.ORE_TITANIUM]]:
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
        if pathfind.fast_pathfind_to(self.rc, self.sense, self.pathfind_target):
            self.econ_explore_timeout = BOT_EXPLORE_TIMEOUT
            self.econ_explore_dir = biased_random_dir(self.rc)
            self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)

    def econ_target(self):
        # Stuck Detection
        if self.rc.get_position() == self.stuck_pos:
            self.stuck_counter += 1
            if self.stuck_counter > BOT_TARGET_STUCK_TIMEOUT:
                self.switch_state(BotState.RECOVER_GOTO_CORE)
                return
        else:
            self.stuck_counter = 0
            self.stuck_pos = self.rc.get_position()

        # Make sure there aren't new developments concerning the ore
        should_connect, _ = self.should_connect_to_ore(self.econ_target_ore, self.econ_target_is_ax)
        if not should_connect:
            self.switch_state(BotState.ECON_EXPLORE)
            self.econ_explore_dir = biased_random_dir(self.rc)
            self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
            return
        
        if not self.sense.is_seen(self.econ_target_ore):
            pathfind.fast_pathfind_to(self.rc, self.sense, self.pathfind_target)
            return
        ore_has = self.sense.get_entity(self.econ_target_ore)

        # Validate Walls
        valid_count = 0
        for d in CARDINAL_DIRECTIONS:
            adj = self.econ_target_ore.add(d)

            if adj == self.pathfind_target: continue
            if not is_in_map(adj, self.rc.get_map_width(), self.rc.get_map_height()):
                valid_count += 1
                continue
            if not self.rc.is_in_vision(adj): continue
            print('wall ', d)

            entt = self.sense.get_entity(adj)
            allied = self.sense.is_allied(adj)
            env = self.sense.get_env(adj)

            if env == Environment.WALL or \
                (entt in ENTITY_VALID_BLOCKAGE_ANY) or \
                (allied and entt in ENTITY_VALID_BLOCKAGE_FRIENDLY):
                valid_count += 1
            else:
                goto = self.econ_target_ore if ore_has in ENTITY_WALKABLE else adj.add(get_best_empty_adj(self.rc, adj, self.core_pos))
                self.rc.draw_indicator_dot(goto, 255, 255, 0)
                if try_destroy(self.rc, self.sense, goto, adj):
                    if self.rc.can_build_barrier(adj):
                        self.rc.build_barrier(adj)
                        valid_count += 1
                return
        
        if valid_count != 3: return
        print('after wall checks')
        # Validate Position
        if self.rc.get_position() == self.econ_target_ore:
            move_dir = self.econ_target_ore.direction_to(self.pathfind_target)
            pathfind.simple_step(self.rc, move_dir)
        elif self.rc.get_position() != self.pathfind_target:
            return pathfind.fast_pathfind_to(self.rc, self.sense, self.pathfind_target)
        
        
        print('harvester validation')
        # Validate Harvester
        if self.sense.get_entity(self.econ_target_ore) != EntityType.HARVESTER and is_adjacent(self.rc.get_position(), self.econ_target_ore):
            print('trydestroy?')
            if not try_destroy(self.rc, self.sense, self.pathfind_target, self.econ_target_ore):
                return
            print('trybuildharvester')
            if self.rc.can_build_harvester(self.econ_target_ore):
                self.rc.build_harvester(self.econ_target_ore)
            else:
                print('couldnt build at ', self.econ_target_ore)
                (ti, ax) = self.rc.get_global_resources()
                print
                return
        
        print('post harvester validation')
        if self.sense.get_entity(self.econ_target_ore) == EntityType.HARVESTER:
            if pathfind.fast_pathfind_to(self.rc, self.sense, self.pathfind_target):
                self.switch_state(BotState.ECON_CONNECT)
                self.econ_connect_final_target = self.compute_best_flow_target()
                self.pathfind_target = self.core_pos

    def econ_connect(self):
        if self.econ_connect_current_target is None or self.econ_connect_current_target == self.rc.get_position() or self.econ_connect_protect_target == self.econ_connect_current_target:
            if self.econ_connect_current_is_final:
                self.switch_state(BotState.ECON_EXPLORE)
                self.econ_explore_dir = biased_random_dir(self.rc)
                self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
                return

            # Compute and cache target because it's wasteful to do everytime we enter this procedure
            
            if self.econ_connect_saved_target is None:
                print('update target')
                self.econ_connect_saved_target, self.econ_connect_saved_is_final = self.compute_next_bridge_target(-1)
                self.econ_connect_protect_target = self.rc.get_position() # if self.econ_connect_current_target is None or self.econ_connect_saved_is_final else None
                if self.econ_connect_saved_target is None:
                    self.switch_state(BotState.ECON_EXPLORE)
                    self.econ_explore_dir = biased_random_dir(self.rc)
                    self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
                    return
                self.econ_connect_saved_is_bridge = self.should_bridge_heuristic(self.rc.get_position(), self.econ_connect_saved_target) or self.econ_connect_saved_is_final
            self.rc.draw_indicator_dot(self.econ_connect_saved_target, 0, 0, 255)
            
            if self.econ_connect_protect_target is not None:
                print('launcher_target')
                if not self.is_launcher_protected(self.econ_connect_protect_target):
                    dir = get_best_placable_adj_with_diag(self.rc, self.econ_connect_protect_target, self.enemy_core_pos)
                    launcher_pos = self.econ_connect_protect_target.add(dir)
                    self.rc.draw_indicator_dot(launcher_pos, 255, 0, 0)
                    if not try_destroy(self.rc, self.sense, self.econ_connect_protect_target, launcher_pos):
                        return
                    if not self.rc.can_build_launcher(launcher_pos):
                        (ti, ax) = self.rc.get_global_resources()
                        print(ti, 'v', self.rc.get_launcher_cost()[0])
                        return
                    self.rc.build_launcher(launcher_pos)

            print('pre-bridge build')
            if self.econ_connect_saved_is_bridge:
                if not (self.sense.is_allied(self.rc.get_position()) and self.sense.get_entity(self.rc.get_position()) == EntityType.BRIDGE):
                    if not try_destroy(self.rc, self.sense, self.rc.get_position(), self.rc.get_position()):
                        return
            
                (ti, ax) = self.rc.get_global_resources()
                if ti < 10: return
                
                if not self.rc.can_build_bridge(self.rc.get_position(), self.econ_connect_saved_target):
                    return

                self.rc.build_bridge(self.rc.get_position(), self.econ_connect_saved_target)
                print('built bridge')
                self.econ_connect_current_run.append(self.rc.get_position())
            
            print('committed')
            # Commit the cached target, then it'll be fine :)
            self.econ_connect_current_target = self.econ_connect_saved_target
            self.econ_connect_current_is_bridge = self.econ_connect_saved_is_bridge
            self.econ_connect_current_is_final = self.econ_connect_saved_is_final
            self.econ_connect_protect_target = None
            self.econ_connect_saved_target = None
            self.econ_connect_saved_is_bridge = False
            self.econ_connect_saved_is_final = False
        
        if self.econ_connect_current_is_bridge:
            if self.econ_connect_current_is_final:
                self.switch_state(BotState.ECON_EXPLORE)
                self.econ_explore_dir = biased_random_dir(self.rc)
                self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
                return

            pathfind.fast_pathfind_to(self.rc, self.sense, self.econ_connect_current_target)
        else:
            (ti, ax) = self.rc.get_global_resources()
            if ti < 10: return
            pathfind.cardinal_pathfind_to(self.rc, self.sense, self.econ_connect_current_target, True)


    def econ_nuke(self):
        pass


    def core_healer(self):
        def not_my_problem(pos: Position) -> bool:
            if self.rc.is_in_vision(pos):
                bb = self.rc.get_tile_builder_bot_id(pos)
                if bb is not None and bb != self.rc.get_id() and self.rc.get_team(bb) == self.rc.get_team():
                    return True # an allied builder bot at location.

            for d in DIRECTIONS:
                adj = pos.add(d)
                if not is_in_map(adj, self.sense.map_width, self.sense.map_height): continue
                if not self.rc.is_in_vision(adj): continue
                bb = self.rc.get_tile_builder_bot_id(adj)
                if bb is None: continue
                if bb == self.rc.get_id(): continue
                if self.rc.get_team(bb) == self.rc.get_team():
                    return True # an allied builder bot adjacent to location.
            return False # vulnerable building that needs healing
        
        if self.core_heal_target is None:
            best_heal_target = None
            best_heal_dist = 10000000
            for bldg in self.rc.get_nearby_buildings():
                p = self.rc.get_position(bldg)
                
                allied = self.rc.get_team(bldg) == self.rc.get_team()
                hp = self.rc.get_hp(bldg)
                max_hp = self.rc.get_max_hp(bldg)
                effective_hp = hp + 4 if not_my_problem(p) else hp
                
                if effective_hp < max_hp:
                    self.rc.draw_indicator_dot(p, 255, 0, 0)
                if allied and (effective_hp < max_hp):
                    d = p.distance_squared(self.core_pos)
                    if d < best_heal_dist:
                        best_heal_dist = d
                        best_heal_target = p
            if best_heal_target is not None:
                heal_dir = get_best_empty_adj_with_diag(self.rc, best_heal_target, self.rc.get_position())
                self.pathfind_target = best_heal_target.add(heal_dir)
                self.core_heal_target = best_heal_target
            else:
                pathfind.fast_pathfind_to(self.rc, self.sense, self.core_pos)
                return
        
        
        if self.core_heal_target is not None:
            self.rc.draw_indicator_dot(self.core_heal_target, 0, 255, 0)

            print('[HEAL]heal target: ', self.core_heal_target)
            if not self.rc.is_in_vision(self.core_heal_target):
                pathfind.fast_pathfind_to(self.rc, self.pathfind_target)
                return
            
            bldg = self.rc.get_tile_building_id(self.core_heal_target)
            if bldg is None:
                self.core_heal_target = None
                pathfind.fast_pathfind_to(self.rc, self.sense, self.core_pos)
                return
            
            if not is_adjacent_with_diag(self.rc.get_position(), self.core_heal_target):
                pathfind.fast_pathfind_to(self.rc, self.sense, self.pathfind_target)
                print('moving to heal target' + str(self.pathfind_target))
                # no return - allow immediate heal

            print('hai')
            if self.rc.can_heal(self.core_heal_target):
                self.rc.heal(self.core_heal_target)
                # no return - allow checks
                print('healed', self.core_heal_target)
                

            if self.rc.is_in_vision(self.core_heal_target):
                bldg = self.rc.get_tile_building_id(self.core_heal_target)
                if bldg is None:
                    self.core_heal_target = None
                    return

                if self.rc.get_hp(bldg) >= self.rc.get_max_hp(bldg):
                    self.core_heal_target = None
                    return
                return
            return
            

    def attack_goto(self):
        # if not self.sense.is_seen(self.enemy_core_pos):
        self.pathfind_target = self.enemy_core_pos
        # else:
        #     if self.pathfind_target == self.rc.get_position() or self.pathfind_target == self.enemy_core_pos:
        #         self.pathfind_target = 
        
        pathfind.fast_pathfind_to(self.rc, self.sense, self.pathfind_target)
        if self.sense.is_seen(self.enemy_core_pos):
            if self.sense.get_entity(self.pathfind_target) != EntityType.CORE:
                self.sense.eliminate_next_symmetry()

        if self.sense.enemy_core_found is not None:
            harvesters = self.sense.entt_index[sense.ENTITY_TYPE_TO_VALUE[EntityType.HARVESTER]]
            for h in harvesters:
                for d in CARDINAL_DIRECTIONS:
                    c = h.add(d)
                    if not is_in_map(c, self.sense.map_width, self.sense.map_height): continue
                    if c in self.sense.transport_attack_blacklist: continue
                    if not self.rc.is_in_vision(c): continue
                    if not is_pos_turretable(self.rc, c): continue
                    
                    if c.distance_squared(self.enemy_core_pos) > GameConstants.GUNNER_VISION_RADIUS_SQ: continue
                    if c in self.sense.ally_builders: continue

                    self.switch_state(BotState.ATTACK_HIJACK)
                    self.attack_target = c
                    self.pathfind_target = c.add(get_best_empty_adj_with_diag(self.rc, c, self.rc.get_position()))
                    return
            
            
            transports = self.sense.entt_index[sense.ENTITY_TYPE_TO_VALUE[EntityType.SPLITTER]] | \
                         self.sense.entt_index[sense.ENTITY_TYPE_TO_VALUE[EntityType.CONVEYOR]] | \
                         self.sense.entt_index[sense.ENTITY_TYPE_TO_VALUE[EntityType.BRIDGE]]
            for c in transports:
                if c in self.sense.transport_attack_blacklist: continue
                if not self.rc.is_in_vision(c): continue
                bldg = self.rc.get_tile_building_id(c)
                
                if self.rc.get_stored_resource_id(bldg) is None: continue
                if c.distance_squared(self.enemy_core_pos) > GameConstants.GUNNER_VISION_RADIUS_SQ: continue
                if c in self.sense.ally_builders: continue

                self.switch_state(BotState.ATTACK_HIJACK)
                self.attack_target = c
                self.pathfind_target = c.add(get_best_empty_adj_with_diag(self.rc, c, self.rc.get_position()))
                return
            
            
    def attack_block_ore(self):
        pass

    def attack_hijack(self):
        if self.attack_target in self.sense.transport_attack_blacklist:
            self.switch_state(BotState.ATTACK_GOTO)
            self.pathfind_target = self.enemy_core_pos
            return

        if not self.rc.is_in_vision(self.attack_target):
            pathfind.fast_pathfind_to(self.rc, self.sense, pathfind.pf_state.goal)
            return

        if self.sense.get_entity(self.attack_target) != EntityType.GUNNER:
            if not try_destroy(self.rc, self.sense, self.pathfind_target, self.attack_target): return
            dir = self.attack_target.direction_to(self.enemy_core_pos)
            if not self.rc.can_build_gunner(self.attack_target, dir): return
            self.rc.build_gunner(self.attack_target, dir)

        self.switch_state(BotState.ATTACK_GOTO)
        self.pathfind_target = self.enemy_core_pos

    def recover_goto_core(self):
        if pathfind.fast_pathfind_to(self.rc, self.sense, self.core_pos):
            self.switch_state(BotState.ECON_EXPLORE)


    ### ========================
    ###         Helpers 
    ### ========================

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
        already_siphoned_dir = Direction.CENTRE
        bot_marked = pos in self.sense.ally_builders and self.rc.get_position() != pos
        not_enough_info = False
        harvester_placable = is_pos_editable(self.rc, pos)
        has_harvester = self.sense.get_entity(pos) == EntityType.HARVESTER
        
        # if bldg is None or (self.rc.get_entity_type(bldg) == EntityType.HARVESTER):
        for d in CARDINAL_DIRECTIONS:
            p = pos.add(d)
            if not is_in_map(p, self.sense.map_width, self.sense.map_height): continue
            if not self.rc.is_in_vision(p):
                not_enough_info = True
                continue
            
            bb = self.rc.get_tile_builder_bot_id(p)
            if bb is not None and self.rc.get_id() != bb:
                if self.rc.get_team(bb) == self.rc.get_team():
                    bot_marked = True

            entt = self.sense.get_entity(p)
            if entt in ENTITY_TRANSPORT:
                allied = self.sense.is_allied(p)
                if allied:
                    already_siphoned = True
                    already_siphoned_dir = d
                else:
                    already_siphoned_dir = d
                
            if is_pos_editable(self.rc, p):
                has_free_side = True
        print(
            "has_free_side:", has_free_side,
            "| already_siphoned:", already_siphoned,
            "| already_siphoned_dir:", already_siphoned_dir,
            "| bot_marked:", bot_marked,
            "| not_enough_info:", not_enough_info,
            "| harvester_placable:", harvester_placable,
            "| has_harvester:", has_harvester
        )
        if bot_marked: return (False, Direction.CENTRE)
        if has_harvester and already_siphoned: return (False, already_siphoned_dir)
        tgt = get_best_empty_adj(self.rc, pos, self.core_pos)
        if not has_harvester and already_siphoned: return (harvester_placable, already_siphoned_dir)
        if has_harvester and not already_siphoned:
            print('ret4', tgt)
            return (not not_enough_info, tgt)
        if not has_harvester and not already_siphoned and harvester_placable: return (not not_enough_info, tgt)

        return (False, Direction.CENTRE)

    def compute_best_flow_target(self) -> int:
        # -1 signifies core, all other values signify edges in the flow graph
        return -1
    
    def compute_next_bridge_target(self, flow_target: int) -> (Position, bool):
        start = self.rc.get_position()

        target_tiles = []
        if flow_target == -1:
            # Core
            target_tiles.extend(self.core_tiles)
        else:
            # Todo
            return (None, False)

        # Prioritize Target Tiles
        best_final_target_dist = 100000000
        best_final_target_tile: Position = None
        for ct in target_tiles:
            if start.distance_squared(ct) <= GameConstants.BRIDGE_TARGET_RADIUS_SQ:
                if not self.rc.is_in_vision(ct): continue
                d = start.distance_squared(ct)
                if d < best_final_target_dist:
                    best_final_target_dist = d
                    best_final_target_tile = ct
        if best_final_target_tile is not None:
            print('directly to target ', flow_target, best_final_target_tile)
            return (best_final_target_tile, True)
        
        # Try all other tiles
        best = None
        best_dist = float('inf')
        build_finish = False
        best_is_to_transport = False
        for t in self.sense.nearby_tiles:
            if start.distance_squared(t) > GameConstants.BRIDGE_TARGET_RADIUS_SQ: continue

            is_to_transport = False
            env = self.sense.get_env(t)
            allied = self.sense.is_allied(t)
            entt = self.sense.get_entity(t)
            if env == Environment.WALL: continue
            if not allied and entt not in ENTITY_WALKABLE: continue
            if allied:
                if entt in ENTITY_TRANSPORT:
                    if self.rc.get_stored_resource_id(self.rc.get_tile_building_id(t)) is not None:
                        continue
                    else:
                        is_to_transport = True
                elif entt not in ENTITY_TRIVIAL:
                    continue

            if t in self.sense.ally_builders: continue

            d = dist_to_nearest_target(t, target_tiles)
            if d < best_dist:
                best_dist = d
                best = t
                best_is_to_transport = is_to_transport

        if best is not None:
            print('intermediate ', flow_target, best)
            return (best, best_is_to_transport)
        return (None, False)

    def should_bridge_heuristic(self, start: Position, end: Position) -> bool:
        if start == end: return False
        if manhattan_distance(start, end) > BRIDGE_USAGE_CUTOFF: return True

        h = manhattan_distance
        heap = [(h(start, end), 0, start)]
        visited = {start: 0}

        while heap:
            f, g, pos = heapq.heappop(heap)
            if g > BRIDGE_USAGE_CUTOFF: continue

            if pos == end: return False
            for d in CARDINAL_DIRECTIONS:
                nxt = pos.add(d)
                ng = g + 1

                if ng > BRIDGE_USAGE_CUTOFF: continue
                if not is_in_map(nxt, self.sense.map_width, self.sense.map_height): continue
                
                env = self.sense.get_env(nxt)
                entt = self.sense.get_entity(nxt)
                allied = self.sense.is_allied(nxt)
                if env == Environment.WALL: continue
                if entt in ENTITY_UNWALKABLE: continue
                if allied and entt in ENTITY_TRANSPORT and nxt is not end: continue
                if self.rc.is_in_vision(nxt) and self.rc.get_tile_builder_bot_id(nxt) is not None: continue

                if not pathfind.cardinal_virtually_navvable(self.rc, nxt, d): continue
                if nxt in visited and visited[nxt] <= ng: continue

                visited[nxt] = ng
                heapq.heappush(heap, (ng + h(nxt, end), ng, nxt))
        return True

    def is_launcher_protected(self, pos: Position) -> bool:
        not_enough_info = False
        for d in DIRECTIONS:
            p = pos.add(d)
            if not is_in_map(p, self.rc.get_map_width(), self.rc.get_map_height()): continue
            if not self.sense.is_seen(p):
                not_enough_info = True
                continue
            if self.sense.get_entity(p) == EntityType.LAUNCHER: return True

        return not_enough_info
