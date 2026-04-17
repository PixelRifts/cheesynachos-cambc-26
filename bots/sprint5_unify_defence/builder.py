import sys
import sense
import pathfind
import random
import heapq
import micro

from bot import Bot
from helpers import *
from procedure import *

from enum import Enum
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants, ResourceType, GameError
from collections import deque

BOT_EXPLORE_TIMEOUT = 12
BOT_TARGET_STUCK_TIMEOUT = 80
TITANIUM_TREND_TARGET = 25
TITANIUM_VALUE_FOR_AX = 300
AXIONITE_ENABLE_ROUND = 200
CORE_DANGER = 20
BRIDGE_USAGE_CUTOFF = 5

class BotJob(Enum):
    ECON = "Econ"
    RUSH = "Rush"
    HEAL = "Heal"

class BotState(Enum):
    ECON_EXPLORE = "Explore"
    ECON_RETURN = "ReturnTo"
    ECON_TARGET  = "Target"
    ECON_CONNECT = "Connect"
    ECON_PLACE_FOUNDRY = "Place Foundry"
    ECON_REMOVE_FURTHER_FOUNDRIES = "Remove Further Foundries"
    ECON_NUKE    = "Nuke"

    DEFENCE_TO_HARVESTER = "Def Harvester"
    DEFENCE_TO_CORE      = "Def Core"
    DEFENCE_STATION      = "Def Stationed"
    DEFENCE_STALKING     = "Def Stalking"

    CORE_HEALER = "Heal"

    ATTACK_GOTO      = "Goto"
    ATTACK_BLOCK_ORE = "Block"
    ATTACK_HIJACK    = "Hijack"
    ATTACK_EXEC_PLAN = "Exec Plan"
    ATTACK_STICK_AROUND = "Stick Around"

    RECOVER_GOTO_CORE = "Core"

NO_STUCK_DETECTION_STATES =  { BotState.ECON_CONNECT, BotState.CORE_HEALER, BotState.ATTACK_EXEC_PLAN, BotState.ECON_PLACE_FOUNDRY }
HEAL_EXCLUDE_STATES =        { BotState.ECON_CONNECT }
MICRO_EXCLUDE_STATES =       { BotState.ECON_EXPLORE, BotState.ECON_CONNECT, BotState.CORE_HEALER, BotState.ECON_TARGET, BotState.ATTACK_EXEC_PLAN, BotState.ECON_PLACE_FOUNDRY }
MICRO_DISRUPT_STATES =       { BotState.ATTACK_GOTO }
MICRO_FOLLOW_ENABLE_STATES = { BotState.ATTACK_GOTO, BotState.ECON_EXPLORE, BotState.ECON_RETURN, BotState.DEFENCE_TO_HARVESTER, BotState.DEFENCE_TO_CORE }

ECON_STATES =                { BotState.ECON_EXPLORE, BotState.ECON_RETURN, BotState.ECON_TARGET, BotState.ECON_CONNECT, BotState.ECON_PLACE_FOUNDRY, BotState.ECON_REMOVE_FURTHER_FOUNDRIES, BotState.ECON_NUKE }
DEFENCE_STATES =             { BotState.DEFENCE_TO_HARVESTER, BotState.DEFENCE_TO_CORE, BotState.DEFENCE_STATION }
ATTACK_STATES =              { BotState.ATTACK_GOTO, BotState.ATTACK_BLOCK_ORE, BotState.ATTACK_HIJACK, BotState.ATTACK_STICK_AROUND }

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
        
        self.map_center_pos = Position(self.sense.map_width // 2, self.sense.map_height // 2)
        self.enemy_core_pos = get_symmetric(self.core_pos, self.sense.map_width, self.sense.map_height, self.sense.symmetries_possible[0])
        self.rush_spawn_pos = self.core_pos.add(self.core_pos.direction_to(self.map_center_pos))
        self.harvester_blacklist = set()
        self.foundry_locked = set()
        self.ore_queue = deque()
        self.ore_queue_set = set()
        self.defence_location = None
        self.healed_this_turn = False

        self.attack_disrupt_cache = {}
        self.attack_blacklist_queue: deque[(Position, int)] = deque()
        self.bridge_continue_blacklist: set[Position] = set()
        self.attack_blacklist_set: set[Position] = set()
        self.shuffled_directions = random.sample(DIRECTIONS, len(DIRECTIONS))
        self.shuffled_cardinal_directions = random.sample(CARDINAL_DIRECTIONS, len(CARDINAL_DIRECTIONS))

        global POSITION_CACHE
        POSITION_CACHE.extend(
            [POSITION_GLOBAL_CACHE[(i // self.sense.map_width) * 50 + (i % self.sense.map_width)] for i in range(self.sense.map_width * self.sense.map_height)]
        )
        
        match self.rc.get_position():
            case self.core_pos: self.job = BotJob.HEAL
            case self.rush_spawn_pos: self.job = BotJob.RUSH
            case _: self.job = BotJob.ECON
        match self.job:
            case BotJob.HEAL: self.switch_state(BotState.CORE_HEALER)
            case BotJob.ECON: self.switch_to_econ()
            case BotJob.RUSH: self.switch_state(BotState.ATTACK_GOTO)
                

    def reset_state_variables(self):
        self.pathfind_target: Position = None
        self.stuck_counter = 0
        self.stuck_pos = self.rc.get_position()
        
        # ECON_EXPLORE
        self.econ_explore_dir: Direction = biased_random_dir(self.rc, self.core_pos)
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
        self.econ_connect_past_pos = self.rc.get_position()

        # DEFENCE_LINE
        self.defence_is_to_core: bool = False
        self.defence_current_target: Position = None
        self.defence_use_fast: bool = False
        self.defence_stalking_bb: int = None
        self.defence_stalking_pos: Position = None

        # HEAL
        self.core_heal_target: Position = None

        # ATTACK
        self.attack_target: Position = None
        self.attack_feeder: Position = None
        self.attack_plan: EntityType = None
        self.attack_plan_dir: Direction = None
        self.attack_from: Position = None
        self.attack_return_to = None
        self.attack_plan_timeout = 30
        self.prev_attack_target_hp = 10000
        
    def switch_state(self, state: BotState):
        self.state = state
        self.state_turn_counter = 0
        self.reset_state_variables()
        print('Switch:', self.state)

    def start_turn(self):
        pathfind.clear()
        print(self.state)
        self.sense.update()
        print(self.sense.ti_trend(), self.sense.ax_trend())
        
        # Attack Blacklist
        now = self.rc.get_current_round()
        q = self.attack_blacklist_queue
        s = self.attack_blacklist_set
        while q and q[0][1] <= now:
            pos, _ = q.popleft()
            s.discard(pos)

        if self.sense.enemy_core_found is not None and len(self.sense.symmetries_possible) == 1:
            self.sense.enemy_core_found = get_symmetric(self.core_pos, self.rc.get_map_width(), self.rc.get_map_height(), self.sense.symmetries_possible[0])

        self.enemy_core_pos = self.sense.enemy_core_found if self.sense.enemy_core_found is not None else \
            get_symmetric(self.core_pos, self.rc.get_map_width(), self.rc.get_map_height(), self.sense.symmetries_possible[0])
        
    def turn(self):
        if self.state not in NO_STUCK_DETECTION_STATES:
            # Stuck Detection
            if self.rc.get_position() == self.stuck_pos:
                self.stuck_counter += 1
                if self.stuck_counter > BOT_TARGET_STUCK_TIMEOUT:
                    self.switch_state(BotState.RECOVER_GOTO_CORE)
                    self.stuck_counter = 0
            else:
                self.stuck_counter = 0
                self.stuck_pos = self.rc.get_position()
        
        if self.rc.get_hp() < self.rc.get_max_hp():
            if self.rc.can_heal(self.rc.get_position()):
                self.rc.heal(self.rc.get_position())
                self.healed_this_turn = True
        elif len(self.sense.heal_targets) != 0 and self.state not in HEAL_EXCLUDE_STATES:
            if self.meta_nearest_heal():
                return
        

        if self.state not in MICRO_EXCLUDE_STATES:
            if len(self.sense.enemy_turrets) != 0:
                self.micro_destroy_turrets()
            elif len(self.sense.enemy_builders) != 0:
                if not self.micro_try_attack() and self.state in MICRO_FOLLOW_ENABLE_STATES:
                    self.micro_follow_bot()
            else:
                if len(self.sense.ally_builders) == 0:
                    self.micro_try_attack()

        match self.state:
            case BotState.ECON_EXPLORE:
                self.econ_explore()
            case BotState.ECON_RETURN:
                self.econ_return_to()
            case BotState.ECON_TARGET:
                self.econ_target()
                if self.econ_target_ore is not None:
                    self.rc.draw_indicator_dot(self.econ_target_ore, 255, 0, 255)
                    self.rc.draw_indicator_dot(self.pathfind_target, 255, 255, 255)
            case BotState.ECON_CONNECT:
                self.econ_connect()
            case BotState.ECON_PLACE_FOUNDRY:
                self.econ_place_foundry()
            case BotState.ECON_REMOVE_FURTHER_FOUNDRIES:
                self.econ_remove_further_foundries()
            case BotState.ECON_NUKE:
                self.econ_nuke()
            
            case BotState.DEFENCE_TO_HARVESTER:
                self.defence_to_harvester()
                if self.defence_current_target is not None:
                    self.rc.draw_indicator_dot(self.defence_current_target, 255, 0, 255)
            case BotState.DEFENCE_TO_CORE:
                self.defence_to_core()
                if self.defence_current_target is not None:
                    self.rc.draw_indicator_dot(self.defence_current_target, 255, 0, 255)
            case BotState.DEFENCE_STATION:
                self.defence_station()
            case BotState.DEFENCE_STALKING:
                self.defence_stalk()
            
            case BotState.CORE_HEALER:
                self.core_healer()

            case BotState.ATTACK_GOTO:
                self.attack_goto()
            case BotState.ATTACK_BLOCK_ORE:
                self.attack_block_ore()
            case BotState.ATTACK_HIJACK:
                self.attack_hijack()
            case BotState.ATTACK_EXEC_PLAN:
                self.attack_exec_plan()

            case BotState.RECOVER_GOTO_CORE:
                self.recover_goto_core()
    
    def end_turn(self):
        # self.sense.visualize()
        pass
        
    ### ========================
    ###     State Functions 
    ### ========================

    # Meta

    def micro_should_station(self):
        pass

    def micro_follow_bot(self):
        best_bb = None
        best_bb_dist = 100000
        best_bb_pos = None
        my_pos = self.rc.get_position()
        for b in self.sense.enemy_builders:
            if not self.rc.is_in_vision(b): continue
            bb = self.rc.get_tile_builder_bot_id(b)
            d = self.rc.get_position(bb).distance_squared(my_pos)
            
            invalid = False
            for dir in DIRECTIONS:
                adj = b.add(dir)
                if adj in self.sense.ally_builders: invalid = True
            if invalid: continue

            if d < best_bb_dist:
                best_bb = bb
                best_bb_dist = d
                best_bb_pos = b

        if best_bb is not None:
            last_state = self.state
            self.switch_state(BotState.DEFENCE_STALKING)
            self.defence_stalking_bb = best_bb
            self.defence_stalking_pos = best_bb_pos
            self.attack_return_to = last_state

    def micro_disrupt(self):
        for t in self.sense.enemy_transports:
            bldg = self.sense.tile_bldg_cache[t]
            rsc = self.rc.get_stored_resource_id(bldg)
            if self.rc.is_in_vision(t) and self.rc.get_tile_builder_bot_id(t) is not None: continue
            if bldg in self.attack_disrupt_cache:
                if rsc != self.attack_disrupt_cache[bldg]:
                    last_state = self.state
                    self.attack_disrupt_cache[bldg] = rsc
                    frm = t.add(get_best_pathable_adj_with_diag(self.rc, t, self.rc.get_position()))
                    self.switch_state(BotState.ATTACK_EXEC_PLAN)
                    self.attack_target = t
                    self.attack_plan = EntityType.BARRIER
                    self.attack_from = frm
                    self.attack_return_to = last_state
                    self.rc.draw_indicator_dot(self.attack_target, 255, 0, 0)
            else: self.attack_disrupt_cache[bldg] = rsc

    def micro_try_attack(self) -> bool:
        is_aggressive = self.state in ATTACK_STATES|DEFENCE_STATES
        budget = self.rc.get_cpu_time_elapsed() + 500
        
        harvesters = self.sense.harvesters

        best_poi = None
        best_score = -10000000

        best_already_has_sentinel = False
        for h in harvesters:
            if self.sense.get_env(h) != Environment.ORE_TITANIUM: continue

            already_has_sentinel = False
            count_turrets = 0
            for d in CARDINAL_DIRECTIONS:
                p = h.add(d)
                if not is_in_map(p, self.sense.map_width, self.sense.map_height): continue
                if not self.rc.is_in_vision(p): continue
                entt = self.sense.get_entity(p)
                if entt in ENTITY_TURRET: count_turrets += 1
                if entt == EntityType.SENTINEL: already_has_sentinel = True

            if count_turrets >= 2:
                continue

            for d in CARDINAL_DIRECTIONS:
                p = h.add(d)
                if not is_in_map(p, self.sense.map_width, self.sense.map_height): continue
                if p in self.attack_blacklist_set: continue
                if p in self.sense.transport_attack_blacklist: continue
                if p in self.sense.ally_builders: continue
                if p in self.sense.enemy_builders: continue
                if not self.rc.is_in_vision(p): continue
                if not is_pos_turretable(self.rc, p): continue

                score, skip = micro.score_attack_poi(self.rc, self.sense, p, self.core_pos)
                if skip: continue
                if score > best_score:
                    best_score = score
                    best_poi = p
                    best_already_has_sentinel = already_has_sentinel
            if self.rc.get_cpu_time_elapsed() > budget: break
            
        
        if self.rc.get_cpu_time_elapsed() < budget and is_aggressive:
            transports = self.sense.enemy_transports
            for c in transports:
                if c in self.attack_blacklist_set: continue
                if c in self.sense.transport_attack_blacklist: continue
                if c in self.sense.ally_builders: continue
                if c in self.sense.enemy_builders: continue
                
                if not self.rc.is_in_vision(c): continue
                bldg = self.rc.get_tile_building_id(c)
                if self.rc.get_stored_resource(bldg) not in RESOURCE_ALLOWED_AMMO: continue
                score, skip = micro.score_attack_poi(self.rc, self.sense, c, self.core_pos)
                if skip: continue
                if score > best_score:
                    best_score = score
                    best_poi = c
                    best_already_has_sentinel = False
                if self.rc.get_cpu_time_elapsed() > budget: break

        if best_poi is not None:
            last_state = self.state
            target, frm, plan, _ = micro.poi_attack_plan(self.rc, self.sense, best_poi, self.enemy_core_pos)
            plan = plan if best_already_has_sentinel else EntityType.SENTINEL
            self.switch_state(BotState.ATTACK_EXEC_PLAN)
            self.attack_target = target
            self.attack_plan = plan
            self.attack_from = frm
            self.attack_return_to = last_state
            self.rc.draw_indicator_dot(self.attack_target, 255, 0, 0)
            return True
        return False

    def micro_destroy_turrets(self):
        already_targeted = False
        candidate_dir = None
        turret_candidate = None
        for t in self.sense.enemy_turrets:
            for d in DIRECTIONS:
                p1 = t.add(d)
                if not is_in_map(p1, self.sense.map_width, self.sense.map_height): continue
                if not self.rc.is_in_vision(p1): continue
                if self.sense.get_env(p1) == Environment.WALL: continue
                if self.sense.get_entity(p1) == EntityType.GUNNER:
                    already_targeted = True
                    break
                if is_getting_ammo(self.rc, self.sense, p1) and is_pos_turretable(self.rc, p1):
                    candidate_dir = d
                    turret_candidate = t
            if turret_candidate is not None: break
        
        if already_targeted: return False
        if turret_candidate is None or candidate_dir is None: return False
        
        last_state = self.state
        p = turret_candidate.add(candidate_dir)
        self.switch_state(BotState.ATTACK_EXEC_PLAN)
        self.attack_target = p
        self.attack_plan = EntityType.GUNNER
        self.attack_plan_dir = candidate_dir.opposite()
        self.attack_from = self.attack_target.add(get_best_pathable_adj_with_diag(self.rc, self.attack_target, self.rc.get_position()))
        self.attack_return_to = last_state

    def meta_nearest_heal(self):
        self.stuck_counter -= 1

        # def not_my_problem(pos: Position) -> bool:
        #     if self.rc.is_in_vision(pos):
        #         bb = self.rc.get_tile_builder_bot_id(pos)
        #         if bb is not None and bb != self.rc.get_id() and self.rc.get_team(bb) == self.rc.get_team():
        #             return True # an allied builder bot at location.

        #     for d in DIRECTIONS:
        #         adj = pos.add(d)
        #         if adj in self.sense.ally_builders:
        #             return True
        #     return False # vulnerable building that needs healing
        
        to_heal = None
        to_heal_dist = 100000
        for t in self.sense.heal_targets:
            d = self.rc.get_position().distance_squared(t)
            if d < to_heal_dist:
                to_heal_dist = d
                to_heal = t
        
        if to_heal is not None:
            moved = False
            self.rc.draw_indicator_dot(to_heal, 0, 255, 0)

            my_pos = self.rc.get_position()
            
            if self.rc.get_position().distance_squared(to_heal) > GameConstants.ACTION_RADIUS_SQ:
                pathfind.silly_pathfind_to(self.rc, to_heal)
                
                if self.rc.get_position() != my_pos:
                    moved = True
                # no return - allow immediate heal

            if self.rc.can_heal(to_heal):
                self.rc.heal(to_heal)
                self.healed_this_turn = True
                # no return - allow checks

            # my_pos = self.rc.get_position()
            # has_enemy_targeting = False
            # launcher_candidate = None
            # for d in DIRECTIONS:
            #     p = my_pos.add(d)
            #     if not is_in_map(p, self.sense.map_width, self.sense.map_height): continue
            #     if p in self.sense.enemy_builders: has_enemy_targeting = True
            #     if is_pos_quickly_turretable(self.rc, p): launcher_candidate = p
            
            # has_enough_ti = self.sense.ti_tracker[-1] > get_ti_cost(self.rc, EntityType.LAUNCHER)
            # if has_enemy_targeting and launcher_candidate is not None and \
            #     has_enough_ti and not self.is_launcher_protected(my_pos):
            #     if self.rc.can_destroy(launcher_candidate):
            #         self.rc.destroy(launcher_candidate)
            #     if self.rc.can_build_launcher(launcher_candidate):
            #         self.rc.build_launcher(launcher_candidate)
            return moved

    # Econ

    def econ_explore(self):
        my_pos = self.rc.get_position()

        # Takeover logic
        budget = min(1300, self.rc.get_cpu_time_elapsed() + 100)
        for b in self.sense.bridges:
            if not self.rc.is_in_vision(b): continue
            bldg = self.rc.get_tile_building_id(b)
            resource = self.rc.get_stored_resource(bldg)
            if not resource: continue
            tgt = self.rc.get_bridge_target(bldg)
            if tgt in self.bridge_continue_blacklist: continue
            allied = self.sense.is_allied(tgt)
            entt = self.sense.get_entity(tgt)
            if self.sense.is_seen(tgt) and not (allied and entt in ENTITY_INFRASTRUCTURE_RESOURCE_SINK):
                if pathfind.fast_pathfind_to(self.rc, self.sense, tgt):
                    is_ax = resource == ResourceType.RAW_AXIONITE
                    self.switch_state(BotState.ECON_CONNECT)
                    self.pathfind_target = self.core_pos
                    self.econ_target_is_ax = is_ax
                
                if pathfind.pf_state.failed:
                    self.bridge_continue_blacklist.add(tgt)
            if self.rc.get_cpu_time_elapsed() > budget:
                print('breaking')
                break
        for b in self.sense.conveyors:
            if not self.rc.is_in_vision(b): continue
            bldg = self.rc.get_tile_building_id(b)
            resource = self.rc.get_stored_resource(bldg)
            if not resource: continue

            tgt = b.add(self.rc.get_direction(bldg))
            if tgt in self.bridge_continue_blacklist: continue
            allied = self.sense.is_allied(tgt)
            entt = self.sense.get_entity(tgt)
            if self.sense.is_seen(tgt) and not (allied and entt in ENTITY_INFRASTRUCTURE_RESOURCE_SINK):
                if pathfind.fast_pathfind_to(self.rc, self.sense, tgt):
                    is_ax = resource == ResourceType.RAW_AXIONITE
                    self.switch_state(BotState.ECON_CONNECT)
                    self.pathfind_target = self.core_pos
                    self.econ_target_is_ax = is_ax
                
                if pathfind.pf_state.failed:
                    self.bridge_continue_blacklist.add(tgt)
            if self.rc.get_cpu_time_elapsed() > budget:
                print('breaking')
                break


        # Pick nearest Titanium Ore to target
        closest_ore = None
        closest_ore_dir = Direction.CENTRE
        closest_ore_is_ax = False
        closest_ore_dist = 10000000
        ores = self.sense.ores
        
        budget = min(1800, self.rc.get_cpu_time_elapsed() + 500)
        for o in ores:
            (should_connect, dir) = self.should_connect_to_ore(o, self.sense.get_env(o) == Environment.ORE_AXIONITE)
            if should_connect and dir != Direction.CENTRE:
                if o not in self.ore_queue_set:
                    self.ore_queue_set.add(o)
                    self.ore_queue.append(o)

                dist = o.distance_squared(self.core_pos)
                if dist < closest_ore_dist:
                    closest_ore_dist = dist
                    closest_ore = o
                    closest_ore_is_ax = self.sense.get_env(o) == Environment.ORE_AXIONITE
                    closest_ore_dir = dir
            if self.rc.get_cpu_time_elapsed() > budget:
                print('breaking')
                break
        
        if closest_ore is not None and not self.should_attack_harvester(closest_ore):
            self.switch_state(BotState.ECON_TARGET)
            self.econ_target_ore = closest_ore
            self.pathfind_target = closest_ore.add(closest_ore_dir)
            self.econ_target_is_ax = closest_ore_is_ax
            return

        if len(self.sense.enemy_turrets) != 0:
            self.micro_destroy_turrets()
        elif len(self.sense.enemy_builders) != 0:
            if not self.micro_try_attack() and self.state in MICRO_FOLLOW_ENABLE_STATES:
                self.micro_follow_bot()

        # Timeout to switch direction after BOT_EXPLORE_TIMEOUT time
        self.econ_explore_timeout -= 1
        if self.econ_explore_timeout == 0:
            self.econ_explore_timeout = BOT_EXPLORE_TIMEOUT
            self.econ_explore_dir = biased_random_dir(self.rc, self.core_pos)
            self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)

        # Actually Pathfind
        if pathfind.fast_pathfind_to(self.rc, self.sense, self.pathfind_target):
            self.econ_explore_timeout = BOT_EXPLORE_TIMEOUT
            self.econ_explore_dir = biased_random_dir(self.rc, self.core_pos)
            self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
    
    def econ_return_to(self):
        print(self.econ_target_ore)
        if not self.rc.is_in_vision(self.econ_target_ore):
            pathfind.fast_pathfind_to(self.rc, self.sense, self.econ_target_ore)
        
        if self.rc.is_in_vision(self.econ_target_ore):
            the_ore = self.econ_target_ore
            is_ax = self.sense.get_env(the_ore) == Environment.ORE_AXIONITE
            (should_connect, dir) = self.should_connect_to_ore(the_ore, is_ax)
            if not should_connect or dir == Direction.CENTRE:
                self.switch_to_econ()

            self.switch_state(BotState.ECON_TARGET)
            self.econ_target_ore = the_ore
            self.pathfind_target = the_ore.add(dir)
            self.econ_target_is_ax = is_ax

    def econ_target(self):
        # Make sure there aren't new developments concerning the ore
        # print('confirm status')
        should_connect, direction = self.should_connect_to_ore(self.econ_target_ore, self.econ_target_is_ax)
        if not should_connect or direction == Direction.CENTRE:
            self.switch_to_econ()
            return
        self.pathfind_target = self.econ_target_ore.add(direction)

        # print('seencheck')
        if not self.sense.is_seen(self.econ_target_ore):
            pathfind.fast_pathfind_to(self.rc, self.sense, self.pathfind_target)
            if pathfind.pf_state.failed:
                self.harvester_blacklist.add(self.econ_target_ore)
                self.switch_to_econ()
            return
        ore_has = self.sense.get_entity(self.econ_target_ore)

        # Validate Walls
        valid_count = 0
        should_turret = len(self.sense.enemy_transports) > 4 or len(self.sense.enemy_builders) > 2 or self.sense.ti_tracker[-1] > 500
        should_turret = should_turret and not self.econ_target_is_ax
        the_entt_to_use = EntityType.SENTINEL if should_turret else EntityType.BARRIER
        for d in self.shuffled_cardinal_directions:
            adj = self.econ_target_ore.add(d)

            if adj == self.pathfind_target: continue
            if not is_in_map(adj, self.sense.map_width, self.sense.map_height):
                valid_count += 1
                continue
            # if not self.rc.is_in_vision(adj): continue

            entt = self.sense.get_entity(adj)
            allied = self.sense.is_allied(adj)
            env = self.sense.get_env(adj)

            if env == Environment.WALL or \
                (entt in ENTITY_VALID_BLOCKAGE_ANY) or \
                (allied and entt in ENTITY_VALID_BLOCKAGE_FRIENDLY):
                if allied and entt == EntityType.SENTINEL: the_entt_to_use = EntityType.BARRIER
                valid_count += 1
            else:
                goto = self.econ_target_ore if ore_has in ENTITY_WALKABLE else adj.add(get_best_empty_adj(self.rc, adj, self.core_pos))
                
                if try_destroy(self.rc, self.sense, goto, adj, ti_min=get_ti_cost(self.rc, the_entt_to_use)):
                    dir = micro.compute_best_turret_dir(self.rc, self.sense, adj, the_entt_to_use, self.enemy_core_pos) if the_entt_to_use != EntityType.BARRIER else None
                    if self.rc.can_build(the_entt_to_use, adj, dir):
                        self.rc.build(the_entt_to_use, adj, dir)
                        valid_count += 1
        
        if valid_count != 3: return
        # Validate Position
        if self.rc.get_position() == self.econ_target_ore:
            move_dir = self.econ_target_ore.direction_to(self.pathfind_target)
            if not self.rc.can_move(move_dir):
                if self.sense.get_entity(self.pathfind_target) == EntityType.BARRIER and self.rc.can_destroy(self.pathfind_target):
                    self.rc.destroy(self.pathfind_target)
            pathfind.simple_step(self.rc, move_dir)
        elif self.rc.get_position() != self.pathfind_target:
            return pathfind.fast_pathfind_to(self.rc, self.sense, self.pathfind_target)
        
        # print('harvester validation')
        # Validate Harvester
        if self.sense.get_entity(self.econ_target_ore) != EntityType.HARVESTER and is_adjacent(self.rc.get_position(), self.econ_target_ore):
            # print('trydestroy?')
            if not try_destroy(self.rc, self.sense, self.pathfind_target, self.econ_target_ore, ti_min=get_ti_cost(self.rc, EntityType.HARVESTER)):
                return
            # print('trybuildharvester')
            if self.rc.can_build_harvester(self.econ_target_ore):
                self.rc.build_harvester(self.econ_target_ore)
            else:
                print('couldnt build at ', self.econ_target_ore)
                # (ti, ax) = self.rc.get_global_resources()
                return
        
        # print('post harvester validation')
        if self.sense.get_entity(self.econ_target_ore) == EntityType.HARVESTER:
            if pathfind.fast_pathfind_to(self.rc, self.sense, self.pathfind_target):
                is_ax = self.econ_target_is_ax
                self.switch_state(BotState.ECON_CONNECT)
                self.pathfind_target = self.core_pos
                self.econ_target_is_ax = is_ax

    def econ_connect(self):
        # Compute next target part
        # print('1')

        if self.econ_connect_current_target is None or self.econ_connect_current_target == self.rc.get_position() or \
            self.econ_connect_protect_target == self.econ_connect_current_target or self.econ_connect_past_pos is None:
            print('recompute')
            if self.econ_connect_current_is_final:
                self.switch_to_possibly_patrol()
                return

            # Compute and cache target because it's wasteful to do everytime we enter this procedure
            # print('2')
            if self.econ_connect_saved_target is None:
                self.econ_connect_saved_target, self.econ_connect_saved_is_final = self.compute_next_bridge_target(self.econ_target_is_ax)
                self.econ_connect_protect_target = self.rc.get_position() # if self.econ_connect_current_target is None or self.econ_connect_saved_is_final else None
                if self.econ_connect_saved_target is None:
                    self.switch_to_econ()
                    return
                self.econ_connect_saved_is_bridge = self.should_bridge_heuristic(self.rc.get_position(), self.econ_connect_saved_target, BRIDGE_USAGE_CUTOFF) or \
                    (self.econ_connect_saved_is_final and self.econ_target_is_ax)
            self.rc.draw_indicator_dot(self.econ_connect_saved_target, 0, 0, 255)
            
            # print('3', self.econ_connect_saved_is_bridge)
            if self.econ_connect_saved_is_bridge:
                if not (self.sense.is_allied(self.rc.get_position()) and self.sense.get_entity(self.rc.get_position()) == EntityType.BRIDGE):
                    if not try_destroy(self.rc, self.sense, self.rc.get_position(), self.rc.get_position()):
                        return
            
                (ti, ax) = self.rc.get_global_resources()
                if ti < 10: return
                
                if not self.rc.can_build_bridge(self.rc.get_position(), self.econ_connect_saved_target):
                    return

                self.rc.build_bridge(self.rc.get_position(), self.econ_connect_saved_target)
                self.econ_connect_current_run.append(self.rc.get_position())
            
            # print('commit')
            # Commit the cached target, then it'll be fine :)
            self.econ_connect_past_pos = self.rc.get_position()
            self.econ_connect_current_target = self.econ_connect_saved_target
            self.econ_connect_current_is_bridge = self.econ_connect_saved_is_bridge
            self.econ_connect_current_is_final = self.econ_connect_saved_is_final
            self.econ_connect_protect_target = None
            self.econ_connect_saved_target = None
            self.econ_connect_saved_is_bridge = False
            self.econ_connect_saved_is_final = False
        
        # print('4')
        # Main part
        if self.econ_connect_current_is_bridge:
            if self.econ_connect_current_is_final:
                if self.econ_target_is_ax:
                    last_state = self.state
                    target_pos = self.econ_connect_current_target
                    my_pos = self.rc.get_position()
                    self.switch_state(BotState.ECON_PLACE_FOUNDRY)
                    self.attack_target = target_pos
                    self.attack_feeder = None
                    self.attack_plan = EntityType.FOUNDRY
                    self.attack_from = target_pos.add(get_best_pathable_adj_with_diag(self.rc, target_pos, my_pos))
                    self.attack_return_to = last_state
                else:
                    self.switch_to_possibly_patrol()
                return
            
            pathfind.fast_pathfind_to(self.rc, self.sense, self.econ_connect_current_target)
            if self.rc.is_in_vision(self.econ_connect_current_target):
                entt = self.sense.get_entity(self.econ_connect_current_target)
                allied = self.sense.is_allied(self.econ_connect_current_target)
                if allied and entt in ENTITY_INFRASTRUCTURE:
                    self.switch_to_possibly_patrol()
                    return

        else:
            # print('5')
            if self.econ_connect_past_pos is not None and self.econ_connect_past_pos != self.rc.get_position():
                pathfind.silly_pathfind_to(self.rc, self.econ_connect_past_pos)
            else:
                if not pathfind.cardinal_pathfind_to(self.rc, self.sense, self.econ_connect_current_target, True):
                    self.econ_connect_past_pos = self.rc.get_position()
                else:
                    self.econ_connect_past_pos = None

    def econ_nuke(self):
        pass

    def econ_place_foundry(self):
        self.rc.draw_indicator_dot(self.attack_target, 255, 0, 0)
        self.rc.draw_indicator_dot(self.attack_from, 0, 255, 0)

        # print('basic pf')
        if not self.rc.is_in_vision(self.attack_target):
            pathfind.fast_pathfind_to(self.rc, self.sense, self.attack_target, ignore_builder_at_tgt=True)
            # pathfind.silly_pathfind_to(self.rc, self.attack_target)
            if not self.rc.is_in_vision(self.attack_target): return
        
        entt = self.sense.get_entity(self.attack_target)
        allied = self.sense.is_allied(self.attack_target)

        # print('uneditable check', self.attack_target)
        if not is_pos_editable(self.rc, self.attack_target):
            print(self.attack_target, 'is uneditable')
            self.switch_back_to_neutral(self.attack_return_to)
            return

        # print('try destroy', self.attack_target)
        if entt == self.attack_plan or (allied and entt in ENTITY_ATTACK_NOREPLACE):
            self.switch_back_to_neutral(self.attack_return_to)
            return
        if not try_destroy(self.rc, self.sense, self.attack_from, self.attack_target, \
            ti_min=get_ti_cost(self.rc, self.attack_plan) + get_ti_cost(self.rc, EntityType.ROAD)): return

        # print('foundry setup', self.attack_target)
        match self.attack_plan:
            case EntityType.FOUNDRY:
                if not self.rc.can_build_foundry(self.attack_target): return
                self.rc.build_foundry(self.attack_target)

        # print('done', self.attack_target)
        self.switch_back_to_neutral(self.attack_return_to)

    def econ_remove_further_foundries(self):
        pass

    # Defence

    def defence_to_harvester(self):
        # Init State
        if self.defence_current_target is None:
            choices = self.sense.ally_transports
            choices = [c for c in choices if c not in self.sense.ally_builders]
            self.defence_current_target = None if len(choices) == 0 else random.choice(choices)
            if self.defence_current_target is None:
                self.switch_to_econ()
                return

        self.defence_follow(self.sense.reverse_feed_graph, BotState.DEFENCE_TO_CORE)
        pass
    
    def defence_to_core(self):
        # Init State
        if self.defence_current_target is None:
            choices = self.sense.ally_transports
            choices = [c for c in choices if c not in self.sense.ally_builders]
            self.defence_current_target = None if len(choices) == 0 else random.choice(choices)
            if self.defence_current_target is None:
                self.switch_to_econ()
                return

        self.defence_follow(self.sense.feed_graph, BotState.DEFENCE_TO_HARVESTER)
        pass
    
    def defence_follow(self, graph, back_is: BotState):
        # Forward Current Target
        if is_adjacent_with_diag(self.rc.get_position(), self.defence_current_target):
            # Iterate Backwards from defence_current_target a max of 5 times
            curr = self.defence_current_target
            go_back = False
            changed = False
            for i in range(2):
                t = graph.get(curr, [])
                t = [j for j in t if self.rc.is_in_vision(j) and self.sense.get_entity(j) in ENTITY_TRANSPORT]
                found = None if len(t) == 0 else random.choice(t)
                if found == None or found in self.sense.ally_builders or \
                    found in self.core_tiles:
                    go_back = True
                    break
                self.defence_use_fast = not is_adjacent(self.rc.get_position(), found)
                curr = found
                changed = True
            
            if go_back and not changed:
                starting_from = curr
                self.switch_state(back_is)
                self.defence_current_target = starting_from
                return

            self.defence_current_target = curr

        # Actually Pathfind
        if self.defence_current_target is not None:
            if self.defence_current_target == self.rc.get_position():
                self.switch_to_econ()
                return
            # if self.defence_use_fast:
            #     pathfind.fast_pathfind_to(self.rc, self.sense, self.defence_current_target, ignore_builder_at_tgt=True)
            # else:
            pathfind.silly_pathfind_to(self.rc, self.defence_current_target)

    def defence_station(self):
        if self.sense.ally_builders > 3:
            self.switch_to_econ()
            self.defence_location = None
            return
        
        if not is_adjacent_with_diag(self.rc.get_position(), self.defence_location):
            pathfind.fast_pathfind_to(self.rc, self.sense, self.defence_location)
            return

        dirs = list(DIRECTIONS)
        random.shuffle(dirs)
        for d in dirs:
            p = self.rc.get_position().add(d)
            if self.rc.can_build_road(p):
                self.rc.build_road(p)
            if self.rc.can_move(d):
                rc.move(d)
                return

        pathfind.silly_pathfind_to(self.rc, self.pathfind_target)

    def defence_stalk(self):
        try:
            self.defence_stalking_pos = self.rc.get_position(self.defence_stalking_bb)
        except GameError:
            self.switch_back_to_neutral(self.attack_return_to)
            return
        
        for dir in DIRECTIONS:
            p = self.defence_stalking_pos.add(dir)
            if p in self.sense.ally_builders:
                self.switch_back_to_neutral(self.attack_return_to)
                return
        
        pathfind.silly_pathfind_to(self.rc, self.defence_stalking_pos)

    # Healer

    def core_healer(self):
        pathfind.silly_pathfind_to(self.rc, self.core_pos)
            
    # Attack

    def attack_goto(self):
        # if self.rc.get_current_round() < 100: self.verify_defences()
        my_pos = self.rc.get_position()

        # Pathfind
        self.pathfind_target = self.enemy_core_pos
        should_astar = True
        if self.sense.is_seen(self.enemy_core_pos) and self.rc.is_in_vision(self.enemy_core_pos):
            should_astar = False
        
        if should_astar:
            pathfind.fast_pathfind_to(self.rc, self.sense, self.pathfind_target)
        else:
            pathfind.silly_pathfind_to(self.rc, self.pathfind_target)

        # # Find econ crippling target
        # budget = min(1200, self.rc.get_cpu_time_elapsed() + 500)
        # # print('regular', self.rc.get_cpu_time_elapsed())
        # closest_harvester = None
        # closest_harvester_dist = 10000000
        # harvesters = self.sense.harvesters
        # for h in harvesters:
        #     if self.should_attack_harvester(h):
        #         dist = h.distance_squared(my_pos)
        #         if dist < closest_harvester_dist:
        #             closest_harvester_dist = dist
        #             closest_harvester = h
            
        #     if self.rc.get_cpu_time_elapsed() > budget:
        #         print('breaking')
        #         break

        # if closest_harvester is not None:
        #     target_dir = get_best_placable_adj_ignorebb(self.rc, closest_harvester, self.rc.get_position())
        #     target_pos = closest_harvester.add(target_dir)
        #     if target_pos not in self.attack_blacklist_set and self.sense.get_entity(target_pos) not in ENTITY_ATTACK_NOREPLACE:
        #         self.switch_state(BotState.ATTACK_EXEC_PLAN)
        #         self.attack_target = target_pos
        #         self.attack_feeder = closest_harvester
        #         self.attack_plan = EntityType.SENTINEL
        #         self.attack_plan_dir = target_pos.direction_to(self.enemy_core_pos)
        #         if self.attack_plan_dir == target_pos.direction_to(closest_harvester): self.attack_plan_dir = self.attack_plan_dir.rotate_left()
        #         self.attack_from = target_pos.add(get_best_pathable_adj_with_diag(self.rc, target_pos, my_pos))
        #         self.attack_return_to_econ = False
        #         self.rc.draw_indicator_dot(target_pos, 255, 0, 0)
        #         return
        

        # Possibly eliminate symmetry
        if self.sense.is_seen(self.enemy_core_pos):
            if self.sense.get_entity(self.pathfind_target) != EntityType.CORE:
                self.sense.eliminate_next_symmetry()

        # Find suitable attack target
        # if self.sense.enemy_core_found is not None:
        #     budget = min(1500, self.rc.get_cpu_time_elapsed() + 500)
        #     # print('atenemycore', self.rc.get_cpu_time_elapsed())
        #     attack_possibilities = []
        #     transports = self.sense.enemy_transports
        #     for c in transports:
        #         if c in self.sense.transport_attack_blacklist: continue
        #         if c in self.attack_blacklist_set: continue
        #         if not self.rc.is_in_vision(c): continue
        #         bldg = self.rc.get_tile_building_id(c)
                
        #         if self.rc.get_stored_resource_id(bldg) is None: continue
        #         if c.distance_squared(self.enemy_core_pos) > GameConstants.GUNNER_VISION_RADIUS_SQ: continue
        #         if c in self.sense.ally_builders: continue

        #         attack_possibilities.append((c, True, None))
        #         if self.rc.get_cpu_time_elapsed() > budget:
        #             print('breaking')
        #             break

        #     # print('atenemycore haarvesters', self.rc.get_cpu_time_elapsed())
        #     for h in harvesters:
        #         for d in CARDINAL_DIRECTIONS:
        #             c = h.add(d)
        #             if not is_in_map(c, self.sense.map_width, self.sense.map_height): continue
        #             if c in self.sense.transport_attack_blacklist: continue
        #             if c in self.attack_blacklist_set: continue
        #             if not self.rc.is_in_vision(c): continue
        #             if not is_pos_turretable(self.rc, c): continue
                    
        #             # Also make sure there are actually enemy bldgs to attack nearby
        #             # if c.distance_squared(self.enemy_core_pos) > GameConstants.GUNNER_VISION_RADIUS_SQ: continue
        #             if c in self.sense.ally_builders: continue

        #             attack_possibilities.append((c, True, h))
        #         if self.rc.get_cpu_time_elapsed() > budget:
        #             print('breaking')
        #             break
            
            # if len(attack_possibilities) > 0:
            #     self.switch_state(BotState.ATTACK_EXEC_PLAN)
            #     c, is_sentinel, feeder = random.choice(attack_possibilities)
            #     self.attack_target = c
            #     self.attack_feeder = feeder
            #     self.attack_plan = EntityType.SENTINEL if is_sentinel else EntityType.GUNNER
            #     self.attack_plan_dir = c.direction_to(self.enemy_core_pos)
            #     if feeder is not None:
            #         if self.attack_plan_dir == c.direction_to(feeder): self.attack_plan_dir = self.attack_plan_dir.rotate_left()
            #     self.attack_from = c.add(get_best_pathable_adj_with_diag(self.rc, c, my_pos))
            #     self.attack_return_to_econ = False
            #     self.rc.draw_indicator_dot(self.attack_target, 255, 0, 0)
            #     return

    def attack_block_ore(self):
        pass

    def attack_exec_plan(self):
        print(self.attack_plan, 'at', self.attack_target)
        self.rc.draw_indicator_dot(self.attack_target, 255, 0, 0)
        self.rc.draw_indicator_dot(self.attack_from, 0, 255, 0)

        # print('timeout check', self.attack_plan_timeout, self.rc.get_cpu_time_elapsed())
        if self.rc.is_in_vision(self.attack_target):
            hp = self.rc.get_hp(self.rc.get_tile_building_id(self.attack_target))
            if hp > self.prev_attack_target_hp:
                if self.attack_plan_timeout > 5: self.attack_plan_timeout = 5
                self.attack_plan_timeout-=1
            if hp == self.prev_attack_target_hp:
                self.attack_plan_timeout -= 1
            self.prev_attack_target_hp = hp
        else:
            self.attack_plan_timeout -= 1
        if self.attack_plan_timeout <= 0:
            expiry = self.rc.get_current_round() + 100
            self.attack_blacklist_queue.append((self.attack_target, expiry))
            self.attack_blacklist_set.add(self.attack_target)
            self.switch_back_to_neutral(self.attack_return_to)
            return
        
        # print('basic pf')
        if not self.rc.is_in_vision(self.attack_target):
            pathfind.fast_pathfind_to(self.rc, self.sense, self.attack_target, ignore_builder_at_tgt=True)
            # pathfind.silly_pathfind_to(self.rc, self.attack_target)
            if not self.rc.is_in_vision(self.attack_target): return

        # Possibly broken logic but still trying
        if not self.rc.get_position() != self.attack_target:
            has_friendly_waiting = False
            for d in Direction:
                p = self.attack_target.add(d)
                if not is_in_map(p, self.sense.map_width, self.sense.map_height): continue
                if not self.rc.is_in_vision(p): continue
                if p in self.sense.ally_builders:
                    has_friendly_waiting = True
                    break
            if has_friendly_waiting:
                expiry = self.rc.get_current_round() + 100
                self.attack_blacklist_queue.append((self.attack_target, expiry))
                self.attack_blacklist_set.add(self.attack_target)
                self.switch_back_to_neutral(self.attack_return_to)
                return
        
        if len(self.sense.enemy_turrets) == 0 and len(self.sense.enemy_builders) == 0:
            self.switch_back_to_neutral(self.attack_return_to)
            return
        
        # Launcher place mode
        my_pos = self.rc.get_position()
        has_enemy_targeting = False
        launcher_candidate = None
        for d in DIRECTIONS:
            p = my_pos.add(d)
            if not is_in_map(p, self.sense.map_width, self.sense.map_height): continue
            if p in self.sense.enemy_builders: has_enemy_targeting = True
            if is_pos_quickly_turretable(self.rc, p): launcher_candidate = p

        has_enough_ti = self.sense.ti_tracker[-1] > (get_ti_cost(self.rc, EntityType.LAUNCHER) * 2)
        if has_enemy_targeting and launcher_candidate is not None and \
            has_enough_ti and not self.is_launcher_protected(my_pos):
            if self.rc.can_destroy(launcher_candidate):
                self.rc.destroy(launcher_candidate)
            if self.rc.can_build_launcher(launcher_candidate):
                self.rc.build_launcher(launcher_candidate)
            return

        # print('poi update check')
        entt = self.sense.get_entity(self.attack_target)
        allied = self.sense.is_allied(self.attack_target)
        if not is_pos_turretable(self.rc, self.attack_target):
            # print(self.attack_target, 'stuff done here')
            expiry = self.rc.get_current_round() + 100
            self.attack_blacklist_queue.append((self.attack_target, expiry))
            self.attack_blacklist_set.add(self.attack_target)
            self.switch_back_to_neutral(self.attack_return_to)
            return

        # print('uneditable check', self.attack_target, self.rc.get_cpu_time_elapsed())
        if not is_pos_turretable(self.rc, self.attack_target) or self.attack_target in self.sense.ally_builders or self.attack_target in self.sense.enemy_builders:
            # print(self.attack_target, 'is uneditable')
            self.switch_back_to_neutral(self.attack_return_to)
            return

        print('try destroy', self.attack_target, self.rc.get_cpu_time_elapsed())
        if entt == self.attack_plan or (allied and entt in ENTITY_ATTACK_NOREPLACE):
            self.switch_back_to_neutral(self.attack_return_to)
            return
        
        print(get_ti_cost(self.rc, self.attack_plan))
        if not try_destroy(self.rc, self.sense, self.attack_from, self.attack_target, \
            ti_min=get_ti_cost(self.rc, self.attack_plan)+20):
            if self.sense.get_entity(self.attack_target) == None: self.attack_plan_timeout += 1
            return
        
        turret_dir = self.attack_plan_dir
        if self.attack_plan in ENTITY_TURRET and self.attack_plan_dir is None:
            turret_dir = micro.compute_best_turret_dir(self.rc, self.sense, self.attack_target, self.attack_plan, self.enemy_core_pos)

        print('attacker setup', self.attack_target)
        match self.attack_plan:
            case EntityType.GUNNER:
                if not self.rc.can_build_gunner(self.attack_target, turret_dir): return
                self.rc.build_gunner(self.attack_target, turret_dir)
            case EntityType.SENTINEL:
                if not self.rc.can_build_sentinel(self.attack_target, turret_dir): return
                self.rc.build_sentinel(self.attack_target, turret_dir)
            case EntityType.BARRIER:
                if not self.rc.can_build_barrier(self.attack_target): return
                self.rc.build_barrier(self.attack_target)

        # print('done', self.attack_target)
        # self.switch_back_to_neutral(self.attack_return_to)
        self.switch_state(BotState.ATTACK_STICK_AROUND)
        self.attack_plan_timeout = 10

    def attack_stick_around(self):
        self.attack_plan_timeout -= 1
        if self.healed_this_turn: self.attack_plan_timeout = 10
        if self.attack_plan_timeout <= 0:
            self.switch_back_to_neutral(BotState.ATTACK_GOTO)
        
        dirs = list(DIRECTIONS)
        random.shuffle(dirs)
        for d in dirs:
            p = self.rc.get_position().add(d)
            if rc.can_build_road(d):
                rc.build_road(d)
            if rc.can_move(d):
                rc.move(d)
                return
        pass

    # Recovery

    def recover_goto_core(self):
        pathfind.fast_pathfind_to(self.rc, self.sense, self.core_pos)

        if self.rc.get_position().distance_squared(self.core_pos) <= 3:
            self.switch_to_econ()
            return

    ### ========================
    ###         Helpers 
    ### ========================

    def should_connect_to_ore(self, pos: Position, is_ax: bool) -> (bool, Direction):
        if pos is None: return (False, Direction.CENTRE)
        if pos in self.harvester_blacklist: return (False, Direction.CENTRE)
        
        (ti, ax) = self.rc.get_global_resources()
        
        if is_ax:
            if ti < TITANIUM_VALUE_FOR_AX or self.rc.get_current_round() < AXIONITE_ENABLE_ROUND:
                return (False, Direction.CENTRE)
        else:
            if (self.sense.ti_trend() > TITANIUM_TREND_TARGET) and self.sense.ax_trend() < 100:
                return (False, Direction.CENTRE)
                
        if not self.rc.is_in_vision(pos): return (False, Direction.CENTRE)
        entt = self.sense.get_entity(pos)
        allied = self.sense.is_allied(pos)
        if entt in ENTITY_TURRET or entt == EntityType.FOUNDRY: return (False, Direction.CENTRE)
        if allied and entt in ENTITY_TRANSPORT: return (False, Direction.CENTRE)
        
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
            if entt in ENTITY_TRANSPORT or entt == EntityType.CORE or entt == EntityType.FOUNDRY:
                allied = self.sense.is_allied(p)
                if allied:
                    already_siphoned = True
                    already_siphoned_dir = d
                else:
                    already_siphoned_dir = d
            
            if is_pos_editable(self.rc, p) and self.sense.get_entity(p) not in ENTITY_VALID_BLOCKAGE_ANY:
                has_free_side = True

        if d == Direction.CENTRE: return (True, Direction.CENTRE)
        if bot_marked: return (False, Direction.CENTRE)
        if has_harvester and already_siphoned: return (False, already_siphoned_dir)
        tgt = get_best_placable_adj_ignorebb(self.rc, pos, self.core_pos)
        if not has_harvester and already_siphoned and not is_ax: return (harvester_placable, already_siphoned_dir)
        if has_harvester and not already_siphoned: return (not not_enough_info, tgt)
        if not has_harvester and not already_siphoned and harvester_placable: return (True, tgt)

        return (False, Direction.CENTRE)

    def compute_next_bridge_target(self, is_ax: bool) -> (Position, bool):
        start = self.rc.get_position()
        target_tiles = self.core_tiles
        
        TARGET_DIST_W = 1.0
        FOUNDRY_DIST_W = 1.0
        TILE_DIST_W = 1.0
        TILE_TRANSPORT_BONUS = 0.0

        if not is_ax:
            best_score = float('-inf')
            best_final_target_tile: Position = None
            for ct in target_tiles:
                if start.distance_squared(ct) > GameConstants.BRIDGE_TARGET_RADIUS_SQ: continue
                if not self.rc.is_in_vision(ct): continue
                score = -TARGET_DIST_W * start.distance_squared(ct)
                if score > best_score:
                    best_score = score
                    best_final_target_tile = ct
            if best_final_target_tile is not None:
                print('directly to target ', best_final_target_tile)
                return (best_final_target_tile, True)

            # for t in self.sense.nearby_tiles:
            #     if start.distance_squared(t) != 1: continue
            #     entt = self.sense.get_entity(t)
            #     if entt not in ENTITY_TRANSPORT: continue
            #     bldg = self.rc.get_tile_building_id(t)
            #     if self.rc.get_stored_resource(bldg) is not None: continue
            #     print('merge one tile away ', t)
            #     return (t, True)
        
        if is_ax:
            best = None
            best_score = float('-inf')
            for t in self.sense.ally_transports:
                if start.distance_squared(t) > GameConstants.BRIDGE_TARGET_RADIUS_SQ: continue
                if self.sense.get_entity(t) != EntityType.CONVEYOR: continue
                bldg = self.rc.get_tile_building_id(t)
                if self.rc.get_stored_resource(bldg) != ResourceType.TITANIUM: continue
                score = -FOUNDRY_DIST_W * dist_to_nearest_target(t, target_tiles)
                if score > best_score:
                    best_score = score
                    best = t
            if best is not None:
                print('merge using foundry ', best)
                return (best, True)
        
        best = None
        best_score = float('-inf')
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
                    resource = self.rc.get_stored_resource_id(self.rc.get_tile_building_id(t))
                    if (not is_ax and resource is not None) or (is_ax and resource != ResourceType.TITANIUM):
                        continue
                    else:
                        is_to_transport = True
                elif entt not in ENTITY_TRIVIAL:
                    continue
            if t in self.sense.ally_builders: continue
            score = -TILE_DIST_W * dist_to_nearest_target(t, target_tiles) + TILE_TRANSPORT_BONUS * is_to_transport
            if score > best_score:
                best_score = score
                best = t
                best_is_to_transport = is_to_transport

        if best is not None:
            print('intermediate ', best)
            return (best, best_is_to_transport)
        return (None, False)

    def astar_test_heuristic(self, start: Position, end: Position, cutoff: int) -> bool:
        if start == end:
            return False

        map_w = self.sense.map_width
        map_h = self.sense.map_height

        start_x, start_y = start.x, start.y
        end_x,   end_y   = end.x,   end.y

        adx = abs(start_x - end_x)
        ady = abs(start_y - end_y)
        if (adx if adx > ady else ady) > cutoff:
            return True

        start_flat = start_y * map_w + start_x
        end_flat   = end_y   * map_w + end_x

        _get_env          = self.sense.get_env
        _get_entity       = self.sense.get_entity
        _is_allied        = self.sense.is_allied
        _is_in_vision     = self.rc.is_in_vision
        _get_tile_builder = self.rc.get_tile_builder_bot_id
        _WALL             = Environment.WALL
        _UNWALKABLE       = ENTITY_UNWALKABLE
        _TRANSPORT        = ENTITY_TRANSPORT

        DIR_TABLE = (
            ( 0, -1, -map_w     ),
            ( 0,  1,  map_w     ),
            ( 1,  0,  1         ),
            (-1,  0, -1         ),
            ( 1, -1,  1 - map_w ),
            (-1, -1, -1 - map_w ),
            ( 1,  1,  1 + map_w ),
            (-1,  1, -1 + map_w ),
        )

        heap    = [(adx if adx > ady else ady, 0, start_flat)]
        visited = {start_flat: 0}

        while heap:
            f, g, pos = heapq.heappop(heap)
            if g > cutoff:
                continue
            if pos == end_flat:
                return False

            px = pos % map_w
            py = pos // map_w

            for dx, dy, d_delta in DIR_TABLE:
                ng = g + 1
                if ng > cutoff: continue

                nxt_x = px + dx
                nxt_y = py + dy
                if nxt_x < 0 or nxt_x >= map_w or nxt_y < 0 or nxt_y >= map_h: continue

                nxt = pos + d_delta

                env  = _get_env(nxt)
                if env == _WALL: continue
                entt = _get_entity(nxt)
                if entt in _UNWALKABLE: continue
                allied = _is_allied(nxt)
                if allied and entt in _TRANSPORT and nxt != end_flat: continue
                if _is_in_vision(POSITION_CACHE[nxt]) and _get_tile_builder(POSITION_CACHE[nxt]) is not None: continue

                if nxt in visited and visited[nxt] <= ng:
                    continue

                visited[nxt] = ng

                hdx = abs(nxt_x - end_x)
                hdy = abs(nxt_y - end_y)
                h   = hdx if hdx > hdy else hdy
                heapq.heappush(heap, (ng + h, ng, nxt))

        return True

    def should_bridge_heuristic(self, start: Position, end: Position, cutoff: int) -> bool:
        if start == end or is_adjacent(start, end): return False

        def check(x, y):
            p = Position(x, y)
            if not is_in_map(p, self.sense.map_width, self.sense.map_height): return True
            if self.sense.get_env(p) == Environment.WALL: return True
            entt = self.sense.get_entity(p)
            allied = self.sense.is_allied(p)
            if entt in ENTITY_UNWALKABLE: return True
            if allied and entt in ENTITY_TRANSPORT and p != end: return True
            if p in self.sense.enemy_builders: return True
            return False

        # try x -> y
        cx, cy = start.x, start.y
        blocked_xy = False
        while cx != end.x:
            cx += 1 if end.x > cx else -1
            if check(cx, cy):
                blocked_xy = True
                break
        if not blocked_xy:
            while cy != end.y:
                cy += 1 if end.y > cy else -1
                if check(cx, cy):
                    blocked_xy = True
                    break
        # try y -> x
        cx, cy = start.x, start.y
        blocked_yx = False
        while cy != end.y:
            cy += 1 if end.y > cy else -1
            if check(cx, cy):
                blocked_yx = True
                break
        if not blocked_yx:
            while cx != end.x:
                cx += 1 if end.x > cx else -1
                if check(cx, cy):
                    blocked_yx = True
                    break
        return blocked_xy and blocked_yx

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

    def should_attack_harvester(self, pos: Position) -> bool:
        if pos is None: return False
        if pos in self.attack_blacklist_set: return False
        if not self.rc.is_in_vision(pos): return False
        if self.sense.get_entity(pos) != EntityType.HARVESTER: return False

        tiles = [pos.add(d) for d in CARDINAL_DIRECTIONS]
        
        has_free_side = False
        not_enough_info = False
        ally_gunners = 0
        ally_sentinels = 0
        enemy_turrets = 0
        barrier_count = 0
        ally_siphon = False
        enemy_siphon = False
        t = [False, False, False, False]

        for i, d in enumerate(CARDINAL_DIRECTIONS):
            p = tiles[i]
            if p in self.attack_blacklist_set: continue
            if not is_in_map(p, self.sense.map_width, self.sense.map_height): continue
            if not self.rc.is_in_vision(p):
                not_enough_info = True
                continue
            
            bb = self.rc.get_tile_builder_bot_id(p)
            if bb is not None and self.rc.get_id() != bb:
                if self.rc.get_team(bb) == self.rc.get_team():
                    return False

            entt = self.sense.get_entity(p)
            allied = self.sense.is_allied(p)
            if entt in ENTITY_TRANSPORT:
                if allied: ally_siphon = True
                else:      enemy_siphon = True
            elif entt == EntityType.BARRIER:
                barrier_count += 1
            elif entt in ENTITY_TURRET:
                if allied:
                    if entt == EntityType.SENTINEL: ally_sentinels += 1
                    else:                           ally_gunners += 1
                else:                               enemy_turrets += 1
            
            if is_pos_editable(self.rc, p) and entt not in ENTITY_VALID_BLOCKAGE_ANY:
                t[i] = True
                has_free_side = True
        
        if not has_free_side or not_enough_info: return False
        return enemy_siphon or not self.sense.is_allied(pos)

    def switch_back_to_neutral(self, to_state: BotState):
        if to_state in ECON_STATES:
            self.switch_to_econ()
        elif to_state == BotState.CORE_HEALER:
            self.switch_state(BotState.CORE_HEALER)
        elif to_state in DEFENCE_STATES:
            self.switch_state(BotState.DEFENCE_TO_HARVESTER)
        else:
            self.switch_state(BotState.ATTACK_GOTO)
            self.pathfind_target = self.enemy_core_pos

    def switch_to_possibly_patrol(self):
        # print('possiblypatrol before', self.rc.get_cpu_time_elapsed())
        # patrol_condition = self.astar_test_heuristic(self.rc.get_position(), self.core_pos, 5)
        patrol_condition = chebyshev_distance(self.rc.get_position(), self.core_pos) >= 5
        # print('possiblypatrol after', self.rc.get_cpu_time_elapsed())
        if not patrol_condition:
            self.switch_to_econ()
        else:
            self.switch_state(BotState.DEFENCE_TO_HARVESTER)
        return

    def switch_to_econ(self):
        if len(self.ore_queue) > 0 and random.randint(0, 4) >= 1:
            selection = self.ore_queue.pop()
            self.ore_queue_set.remove(selection)

            self.switch_state(BotState.ECON_RETURN)
            self.econ_target_ore = selection
        else:
            self.switch_state(BotState.ECON_EXPLORE)
            if self.rc.get_current_round() < 100:
                if is_near_center(self.core_pos, self.sense.map_width, self.sense.map_height):
                    self.econ_explore_dir = self.rc.get_position().direction_to(Position(self.sense.map_width // 2, self.sense.map_height // 2)).opposite()
                else:
                    self.econ_explore_dir = self.rc.get_position().direction_to(Position(self.sense.map_width // 2, self.sense.map_height // 2))
            else:
                self.econ_explore_dir = biased_random_dir(self.rc, self.core_pos)
            self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
