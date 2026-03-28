import sys
import pathfind
import sense
import random

from helpers import *

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants, ResourceType

BOT_EXPLORE_TIMEOUT = 12
AXIONITE_ENABLE_ROUND = 200
NUKE_WAIT_FOR = 50
CORE_DANGER = 20

base_stages = [
    # [
    #     # ( 2, 0, EntityType.SPLITTER, Direction.WEST),
    #     # (-2, 0, EntityType.SPLITTER, Direction.EAST),
    #     # ( 2,  1, EntityType.SENTINEL, Direction.NORTHEAST),
    #     # (-2, -1, EntityType.SENTINEL, Direction.SOUTHWEST),
    #     # ( 2,  1, EntityType.BARRIER, Direction.CENTRE),
    #     # (-2, -1, EntityType.BARRIER, Direction.CENTRE),
    #     # ( 2, -1, EntityType.BARRIER, Direction.CENTRE),
    #     # (-2,  1, EntityType.BARRIER, Direction.CENTRE),
    # ],
    # [
    #     # ( 2,  0, EntityType.SPLITTER, Direction.WEST),
    #     # (-2,  0, EntityType.SPLITTER, Direction.EAST),
    #     # ( 2,  1, EntityType.SENTINEL, Direction.NORTHEAST),
    #     # (-2, -1, EntityType.SENTINEL, Direction.SOUTHWEST),
    #     # ( 2,  1, EntityType.BARRIER, Direction.CENTRE),
    #     # (-2, -1, EntityType.BARRIER, Direction.CENTRE),
    #     # ( 2, -1, EntityType.BARRIER, Direction.CENTRE),
    #     # (-2,  1, EntityType.BARRIER, Direction.CENTRE),
    #     # ( 0,  2, EntityType.BARRIER, Direction.CENTRE),
    #     # (-1,  2, EntityType.BARRIER, Direction.CENTRE),
    #     # ( 1,  2, EntityType.BARRIER, Direction.CENTRE),
    #     # ( 0, -2, EntityType.BARRIER, Direction.CENTRE),
    #     # (-1, -2, EntityType.BARRIER, Direction.CENTRE),
    #     # ( 1, -2, EntityType.BARRIER, Direction.CENTRE),
    # ]
]

class BotState(Enum):
    ECON_EXPLORE = "Explore"
    ECON_TARGET  = "Target"
    ECON_CONNECT = "Connect"
    ECON_NUKE    = "Nuke"

    ATTACK_GOTO      = "Goto"
    ATTACK_BLOCK_ORE = "Block"
    ATTACK_HIJACK    = "Hijack"


class BuilderBot(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        sense.sense_state.setup(rc)

        for i in range(len(base_stages)):
            random.shuffle(base_stages[i])
        
        self.core_pos = self.rc.get_position()
        buildings = rc.get_nearby_buildings(3)
        for b in buildings:
            if rc.get_entity_type(b) == EntityType.CORE:
                self.core_pos = rc.get_position(b)
                break
        self.map_center_pos = Position(self.rc.get_map_width() // 2, self.rc.get_map_height() // 2)
        self.enemy_core_pos = get_symmetric(self.core_pos, self.rc.get_map_width(), self.rc.get_map_height(), sense.sense_state.symmetries_possible[0])
        # self.econ_tracked_ore = set()
        self.base_stage = 0
        
        if rc.get_current_round() == 1:
            self.rusher = False
        else:
            self.rusher = True

        if not self.rusher:
            self.switch_state(BotState.ECON_EXPLORE)
            self.econ_explore_dir = self.core_pos.direction_to(self.rc.get_position())
            if self.econ_explore_dir == Direction.CENTRE: self.econ_explore_dir = biased_random_dir(self.rc)
            self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
        else:
            self.switch_state(BotState.ATTACK_GOTO)
            self.pathfind_target = self.enemy_core_pos

    def reset_state_variables(self):
        self.pathfind_target: Position = None
        self.econ_explore_dir: Direction = Direction.CENTRE
        self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
        self.econ_explore_timeout: int = BOT_EXPLORE_TIMEOUT
        self.econ_target_ore: Position = None
        self.econ_target_is_ax: bool = False
        self.econ_connect_current_target: Position = None
        self.econ_connect_current_run: list[Position] = []
        self.econ_connect_current_should_bridge: bool = True
        self.econ_connect_launcher_where: Position = None
        self.econ_connect_then_explore: bool = False
        self.econ_protect_turret_loc = None
        self.econ_protect_turret_dir = Direction.CENTRE
        self.econ_protect_return_loc = self.rc.get_position()
        self.econ_connect_came_from_placement: bool = False

        self.attack_target: Position = None
        self.attack_replace_blacklist = set()
        
        # Some states want sub-states
        self.state_custom_sub_state: int = 0
    
    def switch_state(self, state: BotState):
        self.state = state
        self.state_turn_counter = 0
        self.reset_state_variables()

    def start_turn(self):
        sense.update_sense(self.rc)
        print(sense.sense_state.symmetries_possible)
        if sense.sense_state.enemy_core_found is not None:
            self.enemy_core_pos = sense.sense_state.enemy_core_found
        else:
            self.enemy_core_pos = get_symmetric(self.core_pos, self.rc.get_map_width(), self.rc.get_map_height(), sense.sense_state.symmetries_possible[0])
    
    def turn(self):
        match self.state:
            case BotState.ECON_EXPLORE:
                self.econ_explore()
            case BotState.ECON_TARGET:
                self.econ_target()
            case BotState.ECON_CONNECT:
                self.econ_connect()
                if self.econ_connect_current_target is not None:
                    self.rc.draw_indicator_dot(self.econ_connect_current_target, 255, 0, 255 if self.econ_connect_current_should_bridge else 0)
            case BotState.ECON_NUKE:
                self.econ_nuke()
            
            case BotState.ATTACK_GOTO:
                self.attack_goto()
            case BotState.ATTACK_BLOCK_ORE:
                self.attack_block_ore()
            case BotState.ATTACK_HIJACK:
                self.attack_hijack()
    
    def econ_explore(self):
        # Defence Plan Guarantee
        # if not self.verify_defences():
        #     return

        if self.rusher:
            self.switch_state(BotState.ATTACK_GOTO)
            self.pathfind_target = self.enemy_core_pos
            return

        # if self.state_turn_counter == 1:
        #     if len(self.econ_tracked_ore) > 0:
        #         track = self.econ_tracked_ore.pop()
        #         self.pathfind_target = track

        # Possibly Find and Target Ore TITANIUM
        decided_ore = None
        decided_dir = Direction.CENTRE
        decided_is_ax = False
        decided_min_distance = 1000000
        for pos in self.rc.get_nearby_tiles():
            env = self.rc.get_tile_env(pos)
            if env == Environment.ORE_TITANIUM or env == Environment.ORE_AXIONITE:
                (should_connect, dir) = self.should_connect_to_ore(pos, env == Environment.ORE_AXIONITE)
                dist = pos.distance_squared(self.rc.get_position())
                if should_connect:
                    # self.econ_tracked_ore.add(pos)
                    if dist < decided_min_distance:
                        decided_min_distance = dist
                        decided_dir = dir
                        decided_ore = pos
                        decided_is_ax = env == Environment.ORE_AXIONITE
                    
        if decided_ore is not None:
            # self.econ_tracked_ore.remove(decided_ore)
            self.switch_state(BotState.ECON_TARGET)
            self.econ_target_ore = decided_ore
            self.pathfind_target = decided_ore.add(decided_dir)
            self.econ_target_is_ax = decided_is_ax
            return

        if sense.sense_state.nearest_enemy_transport is not None:
            if self.rc.get_current_round() > NUKE_WAIT_FOR or sense.sense_state.nearest_enemy_transport.distance_squared(self.core_pos) < CORE_DANGER:
                self.switch_state(BotState.ECON_NUKE)
                self.pathfind_target = sense.sense_state.nearest_enemy_transport

        # Timeout direction switch
        self.econ_explore_timeout -= 1
        if self.econ_explore_timeout == 0:
            self.econ_explore_timeout = BOT_EXPLORE_TIMEOUT
            self.econ_explore_dir = biased_random_dir(self.rc)
            self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)

        # Actual Move
        # if self.rc.can_move(self.econ_explore_dir):
        #     self.rc.move(self.econ_explore_dir)
        # elif self.rc.is_tile_empty(next_pos):
        #     if self.rc.can_build_road(next_pos):
        #         self.rc.build_road(next_pos)
        #         if self.rc.can_move(self.econ_explore_dir):
        #             self.rc.move(self.econ_explore_dir)

        # if self.rc.get_current_round() < 50:
        # next_pos = self.rc.get_position().add(self.econ_explore_dir)
        # if not pathfind.is_in_map(next_pos, self.rc.get_map_width(), self.rc.get_map_height()):
        #     self.econ_explore_dir = biased_random_dir(self.rc)
        #     return
        # if self.rc.can_move(self.econ_explore_dir):
        #     self.rc.move(self.econ_explore_dir)
        # elif self.rc.is_tile_empty(next_pos):
        #     if self.rc.can_build_road(next_pos):
        #         self.rc.build_road(next_pos)
        #         if self.rc.can_move(self.econ_explore_dir):
        #             self.rc.move(self.econ_explore_dir)
        # else:
        #     self.econ_explore_dir = biased_random_dir(self.rc)
        # else:
        if pathfind.fast_pathfind_to(self.rc, self.pathfind_target):
            self.econ_explore_timeout = BOT_EXPLORE_TIMEOUT
            self.econ_explore_dir = biased_random_dir(self.rc)
            self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)

    def econ_target(self):
        should_connect, _ = self.should_connect_to_ore(self.econ_target_ore, self.econ_target_is_ax)
        if not should_connect:
            self.switch_state(BotState.ECON_EXPLORE)
            self.econ_explore_dir = biased_random_dir(self.rc)
            self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
            return

        if self.rc.is_in_vision(self.econ_target_ore):
            bldg = self.rc.get_tile_building_id(self.econ_target_ore)
            if bldg is not None and self.rc.get_entity_type(bldg) == EntityType.HARVESTER and is_adjacent(self.rc.get_position(), self.econ_target_ore):
                self.switch_state(BotState.ECON_CONNECT)
                self.pathfind_target = self.core_pos
                return

        if self.state_custom_sub_state == 0 or self.state_custom_sub_state == 1:
            # --- move onto ore ---
            if self.state_custom_sub_state == 0:
                if self.rc.get_position() != self.econ_target_ore:
                    if pathfind.fast_pathfind_to(self.rc, self.econ_target_ore):
                        self.state_custom_sub_state = 1
                
            # --- standing on ore: build barriers around ---
            valid_count = 0
            for d in CARDINAL_DIRECTIONS:
                adj = self.econ_target_ore.add(d)

                if adj == self.pathfind_target: continue
                if not is_in_map(adj, self.rc.get_map_width(), self.rc.get_map_height()): continue
                if not self.rc.is_in_vision(adj): continue

                if get_building_type(self.rc, adj) == EntityType.BARRIER or is_friendly_transport(self.rc, adj) or \
                    self.rc.get_tile_env(adj) == Environment.WALL:
                    valid_count += 1
                else:
                    if try_destroy(self.rc, self.econ_target_ore, adj):
                        if self.rc.can_build_barrier(adj):
                            self.rc.build_barrier(adj)
                            valid_count += 1
                    else:
                        return
                    
            if valid_count != 3: return
            self.state_custom_sub_state = 2

        if self.state_custom_sub_state == 2:
            # --- move off ore to pathfind_target ---
            move_dir = self.econ_target_ore.direction_to(self.pathfind_target)
            if self.rc.get_position() == self.econ_target_ore:
                pathfind.simple_step(self.rc, move_dir)
                return

            # --- now adjacent: place harvester ---
            if is_adjacent(self.rc.get_position(), self.econ_target_ore):
                if not try_destroy(self.rc, self.pathfind_target, self.econ_target_ore):
                    return

                if self.rc.can_build_harvester(self.econ_target_ore):
                    self.rc.build_harvester(self.econ_target_ore)
                    return

    def econ_connect(self):
        # Place a launcher to protect this place
        if self.state_custom_sub_state == 10:
            self.econ_connect_came_from_placement = True
            
            if try_destroy(self.rc, self.rc.get_position(), self.econ_connect_launcher_where):
                if self.rc.can_build_launcher(self.econ_connect_launcher_where):
                    self.rc.build_launcher(self.econ_connect_launcher_where)
                    self.state_custom_sub_state = 0
            else:
                return

            if self.econ_connect_then_explore:
                self.switch_state(BotState.ECON_EXPLORE)
                self.econ_explore_dir = biased_random_dir(self.rc)
                self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
                return
        
        # TODO maybe remove
        if self.state_custom_sub_state != 0: return

        final_marked = False
        if self.econ_connect_current_target is not None and self.rc.get_position() != self.econ_connect_current_target:
            if self.econ_connect_current_should_bridge:
                pathfind.fast_pathfind_to(self.rc, self.econ_connect_current_target)
            else:
                (got_to_target, preempted) = pathfind.preemptable_cardinal_pathfind_to(self.rc, self.econ_connect_current_target, True)
                if got_to_target:
                    final_marked = got_to_target
                self.econ_connect_current_run.append(self.rc.get_position())
                if preempted:
                    print('final one apparently')
                    self.switch_state(BotState.ECON_EXPLORE)
                    self.econ_explore_dir = biased_random_dir(self.rc)
                    self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
                    return
        else:
            if not self.econ_connect_came_from_placement:
                bldg = self.rc.get_tile_building_id(self.rc.get_position())
                entt = get_building_type(self.rc, self.rc.get_position())
                allied = self.rc.get_team(bldg) == self.rc.get_team()
                already_connected = False
                if allied and (entt == EntityType.ROAD or entt == EntityType.CONVEYOR or entt == EntityType.BRIDGE):
                    self.rc.destroy(self.rc.get_position())
                elif not allied:
                    if self.rc.can_fire(self.rc.get_position()):
                        self.rc.fire(self.rc.get_position())
            self.econ_connect_came_from_placement = False

            (best_target, final_one, is_to_core) = self.compute_best_bridge_target(self.econ_target_is_ax)
            self.econ_connect_current_should_bridge = (not pathfind.is_tile_within_n_cardinal_steps(self.rc, self.rc.get_position(), best_target, 2) or is_to_core)

            if self.econ_connect_current_should_bridge:
                if self.rc.can_build_bridge(self.rc.get_position(), best_target):
                    self.rc.build_bridge(self.rc.get_position(), best_target)
                    self.econ_connect_current_run.append(self.rc.get_position())
                    final_marked = True
                else:
                    # print('best_target=',best_target, file=sys.stderr
                    return

            if not self.is_launcher_protected(self.rc.get_position()):
                self.state_custom_sub_state = 10
                dir = get_best_placable_adj_with_diag(self.rc, self.rc.get_position(), self.enemy_core_pos)
                self.econ_connect_launcher_where = self.rc.get_position().add(dir)
                self.econ_connect_then_explore = final_one and final_marked
                return
            
            self.econ_connect_current_target = best_target

            if final_one and final_marked:
                print('final one apparently')
                self.switch_state(BotState.ECON_EXPLORE)
                self.econ_explore_dir = biased_random_dir(self.rc)
                self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
                return

    def econ_nuke(self):
        if pathfind.fast_pathfind_to(self.rc, self.pathfind_target):
            if not is_in_map(self.pathfind_target, self.rc.get_map_width(), self.rc.get_map_height()) or not self.rc.is_in_vision(self.pathfind_target):
                self.switch_state(BotState.ECON_EXPLORE)
                self.econ_explore_dir = biased_random_dir(self.rc)
                self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
                return
            
            bldg = self.rc.get_tile_building_id(self.pathfind_target)
            is_ally = bldg is None or self.rc.get_team(bldg) == self.rc.get_team()
            if not is_ally:
                if self.rc.can_fire(self.pathfind_target):
                    self.rc.fire(self.pathfind_target)
            else:
                self.switch_state(BotState.ECON_EXPLORE)
                self.econ_explore_dir = biased_random_dir(self.rc)
                self.pathfind_target = get_furthest_tile_in_dir(self.rc, self.rc.get_position(), self.econ_explore_dir)
                return

    def attack_goto(self):
        self.pathfind_target = self.enemy_core_pos
        
        pathfind.fast_pathfind_to(self.rc, self.pathfind_target)
        if self.rc.is_in_vision(self.pathfind_target):
            if get_building_type(self.rc, self.pathfind_target) != EntityType.CORE:
                sense.eliminate_next_symmetry()
        
        if sense.sense_state.enemy_core_found is not None:
            max_dist = -1000000
            picked_bldg = None
            for bldg in self.rc.get_nearby_buildings():
                p = self.rc.get_position(bldg)
                if not self.rc.is_in_vision(p): continue
                entt = self.rc.get_entity_type(bldg)
                allied = self.rc.get_team(bldg) == self.rc.get_team()
                
                bb_there = self.rc.get_tile_builder_bot_id(p)
                if bb_there is not None and self.rc.get_team(bb_there) == self.rc.get_team(): continue
                
                if is_enemy_transport(self.rc, p):
                    if p in sense.sense_state.attack_replace_blacklist: continue
                    if self.rc.get_stored_resource_id(bldg) is None: continue
                    
                    d_to_me = p.distance_squared(self.rc.get_position())
                    d_to_core = p.distance_squared(self.enemy_core_pos)
                    if d_to_me > max_dist and (d_to_core <= GameConstants.GUNNER_VISION_RADIUS_SQ + 1):
                        max_dist = d_to_me
                        picked_bldg = p
                elif entt == EntityType.HARVESTER:
                    for d in CARDINAL_DIRECTIONS:
                        off_p = p.add(d)
                        if not is_in_map(off_p, self.rc.get_map_width(), self.rc.get_map_height()): continue
                        if not self.rc.is_in_vision(off_p): continue
                        if not is_pos_turretable(self.rc, off_p): continue
                        
                        d_to_me = off_p.distance_squared(self.rc.get_position())
                        d_to_core = off_p.distance_squared(self.enemy_core_pos)
                        if d_to_me > max_dist and (d_to_core <= GameConstants.GUNNER_VISION_RADIUS_SQ + 1):
                            max_dist = d_to_me
                            picked_bldg = off_p
        
            if picked_bldg is not None:
                self.switch_state(BotState.ATTACK_HIJACK)
                self.attack_target = picked_bldg
                return
        # else:
        #     for p in self.rc.get_nearby_tiles():
        #         if not self.rc.is_in_vision(p): continue
        #         env = self.rc.get_tile_env(p)
        #         bldg = self.rc.get_tile_building_id(p)
        #         if bldg is not None:
        #             allied = self.rc.get_team(bldg) == self.rc.get_team()
        #             entt = self.rc.get_entity_type()
        #             if entt == EntityType.HARVESTER: continue
        #             if not allied and not is_enemy_transport(self.rc, p):
        #                 continue
        #         if env == Environment.ORE_TITANIUM or env == Environment.ORE_AXIONITE:
        #             if self.pathfind_target.distance_squared(self.rc.get_position()) >= self.pathfind_target.distance_squared(p):
        #                 enemy_core = self.pathfind_target
        #                 self.switch_state(BotState.ATTACK_BLOCK_ORE)
        #                 self.pathfind_target = p.add(get_best_empty_adj_with_diag(self.rc, p, enemy_core))
        #                 self.econ_target_ore = p
        #                 return
        

    def attack_block_ore(self):
        if pathfind.fast_pathfind_to(self.rc, self.pathfind_target):
            if try_destroy(self.rc, self.pathfind_target, self.econ_target_ore):
                if self.rc.can_build_barrier(self.econ_target_ore):
                    self.rc.build_barrier(self.econ_target_ore)
            if self.state_custom_sub_state == 1:
                self.switch_state(BotState.ATTACK_GOTO)
                self.pathfind_target = get_symmetric(self.core_pos, self.rc.get_map_width(), self.rc.get_map_height(), sense.sense_state.symmetries_possible[0])
                return
            self.state_custom_sub_state = 1
    
    def attack_hijack(self):
        if self.attack_target in sense.sense_state.attack_replace_blacklist:
            self.switch_state(BotState.ATTACK_GOTO)
            self.pathfind_target = self.enemy_core_pos
            return

        if self.state_custom_sub_state == 0:
            if self.rc.is_in_vision(self.attack_target):
                bb_there = self.rc.get_tile_builder_bot_id(self.attack_target)
                if bb_there is not None and self.rc.get_team(bb_there) == self.rc.get_team():
                    self.switch_state(BotState.ATTACK_GOTO)
                    self.pathfind_target = self.enemy_core_pos
                    return

            if pathfind.fast_pathfind_to(self.rc, self.attack_target):
                self.state_custom_sub_state = 1

        elif self.state_custom_sub_state == 1:
            
            if not self.rc.is_tile_empty(self.attack_target):
                if self.rc.can_destroy(self.attack_target):
                    self.rc.destroy(self.attack_target)
                
                if self.rc.can_fire(self.rc.get_position()):
                    self.rc.fire(self.rc.get_position())
            else:
                self.pathfind_target = self.rc.get_position().add(get_empty_adj_with_diag(self.rc, self.rc.get_position()))
                self.state_custom_sub_state = 2
            
        elif self.state_custom_sub_state == 2:
            if pathfind.fast_pathfind_to(self.rc, self.pathfind_target):
                dir = self.attack_target.direction_to(self.enemy_core_pos)
                if self.rc.can_build_sentinel(self.attack_target, dir):
                    self.rc.build_sentinel(self.attack_target, dir)
                elif self.rc.can_build_gunner(self.attack_target, dir):
                    self.rc.build_gunner(self.attack_target, dir)
                
                if not self.rc.is_in_vision(self.attack_target):
                    self.switch_state(BotState.ATTACK_GOTO)
                    self.pathfind_target = self.enemy_core_pos
                else:
                    entt = get_building_type(self.rc, self.attack_target)
                    if entt == EntityType.SENTINEL or entt == EntityType.GUNNER:
                        self.switch_state(BotState.ATTACK_GOTO)
                        self.pathfind_target = self.enemy_core_pos

        else:
            self.switch_state(BotState.ATTACK_GOTO)
            self.pathfind_target = self.enemy_core_pos


    def end_turn(self):
        if self.pathfind_target is not None: self.rc.draw_indicator_line(self.rc.get_position(), self.pathfind_target, 220, 50, 50)
        print(self.state)
        # sense.draw_feed_graph(self.rc)
        pass


    # CORE DEFENCE PLAN
    
    def get_defence_plan(self):
        (ti, ax) = self.rc.get_global_resources()
        if self.base_stage == 0:
            if self.rc.get_current_round() > AXIONITE_ENABLE_ROUND and ti > 500:
                self.base_stage = 1
            p1 = Position(self.core_pos.x + 2, self.core_pos.y - 1)
            p2 = Position(self.core_pos.x - 2, self.core_pos.y + 1)
            if (is_in_map(p1, self.rc.get_map_width(), self.rc.get_map_height()) and self.rc.is_in_vision(p1) and get_building_type(self.rc, p1) == EntityType.FOUNDRY) or \
                (is_in_map(p2, self.rc.get_map_width(), self.rc.get_map_height()) and self.rc.is_in_vision(p2) and get_building_type(self.rc, p2) == EntityType.FOUNDRY):
                self.base_stage = 1
        
        if self.base_stage < len(base_stages):
            return base_stages[self.base_stage]
        else: return []

    def verify_defences(self) -> bool:
        plan = self.get_defence_plan()
        for dx, dy, desired_type, dir in plan:
            target = Position(self.core_pos.x + dx, self.core_pos.y + dy)

            if not is_in_map(target, self.rc.get_map_width(), self.rc.get_map_height()): continue
            if not self.rc.is_in_vision(target): continue
            env = self.rc.get_tile_env(target)
            if env == Environment.WALL: continue

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
            
            if self.rc.get_position() == target and self.rc.is_tile_empty(target):
                move_dir = get_empty_adj(self.rc, target)
                new_pos = target.add(move_dir)
                pathfind.fast_pathfind_to(self.rc, new_pos)

            if not self.rc.is_tile_empty(target):
                if self.rc.can_destroy(target):
                    self.rc.destroy(target)
                elif self.rc.can_fire(target):
                    self.rc.fire(target)
            
            if desired_type == EntityType.LAUNCHER:
                # print('launcher????', file=sys.stderr)
                if self.rc.can_build_launcher(target):
                    self.rc.build_launcher(target)
                    
            elif desired_type == EntityType.SPLITTER:
                # print('splitter????', file=sys.stderr)
                if self.rc.can_build_splitter(target, dir):
                    self.rc.build_splitter(target, dir)
                    
            elif desired_type == EntityType.SENTINEL:
                # print('splitter????', file=sys.stderr)
                if self.enemy_core_pos is not None:
                    dir = target.direction_to(self.enemy_core_pos)
                else:
                    temp_enemy_core_pos = get_symmetric(self.core_pos, self.rc.get_map_width(), self.rc.get_map_height(), sense.sense_state.symmetries_possible[0])
                    dir = target.direction_to(temp_enemy_core_pos)

                if self.rc.can_build_sentinel(target, dir):
                    self.rc.build_sentinel(target, dir)

            elif desired_type == EntityType.BARRIER:
                # print('splitter????', file=sys.stderr)
                if self.rc.can_build_barrier(target):
                    self.rc.build_barrier(target)
                    
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
            pos = Position(core.x + dx, core.y + dy)
            if not is_in_map(pos, width, height): continue
            if not self.rc.is_in_vision(pos): continue
            env = self.rc.get_tile_env(pos)
            if env == Environment.WALL: continue
            if entity_type == EntityType.SPLITTER:
                core_splitter_tiles.append(pos)
            elif entity_type == EntityType.FOUNDRY:
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
                    if get_building_type(rc, ct) == EntityType.SPLITTER:
                        bldg = rc.get_tile_building_id(ct)
                        if rc.get_stored_resource(bldg) is not None:
                            continue

                    d = start.distance_squared(ct)
                    if d < best_core_dist:
                        best_core_dist = d
                        best_core_tile = ct
            if best_core_tile is not None:
                print('track1', best_core_tile)
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

        # --- 2. reuse existing bridge/conveyor/splitter if it's necessary to be conservative ---
        # (ti, ax) = rc.get_global_resources()
        # if sense.ti_ever_increased():
        #     best_bridge = None
        #     best_bridge_dist = float('inf')
            
        #     for dx in range(-3, 4):
        #         for dy in range(-3, 4):
        #             if dx*dx + dy*dy > GameConstants.BRIDGE_TARGET_RADIUS_SQ:
        #                 continue

        #             pos = Position(start.x + dx, start.y + dy)

        #             if not is_in_map(pos, width, height):
        #                 continue
        #             if not rc.is_in_vision(pos):
        #                 continue

        #             building_id = rc.get_tile_building_id(pos)
        #             if building_id is None: continue
        #             if rc.get_team(building_id) != rc.get_team(): continue

        #             if rc.get_entity_type(building_id) != EntityType.BRIDGE and rc.get_entity_type(building_id) != EntityType.CONVEYOR and rc.get_entity_type(building_id) != EntityType.SPLITTER:
        #                 continue
        #             if self.econ_connect_current_run.__contains__(pos):
        #                 continue
                    
        #             testing_resource = ResourceType.RAW_AXIONITE if connecting_ax else ResourceType.TITANIUM
        #             if rc.get_stored_resource(building_id) != testing_resource:
        #                 continue

        #             d = dist_to_core(pos)
        #             if d < best_bridge_dist and self_to_core_dist > d:
        #                 best_bridge_dist = d
        #                 best_bridge = pos

        #     if best_bridge is not None:
        #         print('track3', best_bridge_dist, self_to_core_dist)
        #         return (best_bridge, True, False)

        # --- 3. pick best new bridge position ---
        best = None
        best_dist = float('inf')
        build_finish = False

        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if dx*dx + dy*dy > GameConstants.BRIDGE_TARGET_RADIUS_SQ:
                    continue

                is_to_existing_transport = False
                pos = Position(start.x + dx, start.y + dy)

                if not is_in_map(pos, width, height):
                    continue
                if not rc.is_in_vision(pos):
                    continue
                if rc.get_tile_env(pos) == Environment.WALL:
                    continue

                bldg = rc.get_tile_building_id(pos)
                if bldg is not None:
                    entt = rc.get_entity_type(bldg)
                    if rc.get_team(bldg) != rc.get_team():
                        continue
                    if entt != EntityType.ROAD and entt != EntityType.BRIDGE and entt != EntityType.CONVEYOR and entt != EntityType.SPLITTER:
                        continue
                    if self.econ_connect_current_run.__contains__(pos):
                        continue
                    if entt != EntityType.ROAD:
                        if rc.get_stored_resource(bldg) is not None:
                            continue
                        is_to_existing_transport = True

                d = dist_to_core(pos)
                
                if d < best_dist:
                    best_dist = d
                    best = pos
                    
                    build_finish = is_to_existing_transport

        print('track4', best if best is not None else start, build_finish)
        return (best if best is not None else start, build_finish, False)
    
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
        has_harvester = get_building_type(self.rc, pos) == EntityType.HARVESTER
        
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
    
    def get_best_protector_dir(self, pos: Position) -> (bool, Position, Direction):
        # if not sense.ti_ever_increased(): return (False, None, Direction.CENTRE)
        if pos is None: return (False, None, Direction.CENTRE)

        free_pos = None
        best_dir = None
        has_turret = False
        for d in CARDINAL_DIRECTIONS:
            p = pos.add(d)
            if not is_in_map(p, self.rc.get_map_width(), self.rc.get_map_height()): continue
            if not self.rc.is_in_vision(p): continue
            
            env = self.rc.get_tile_env(p)
            if env != Environment.EMPTY: continue

            bldg = self.rc.get_tile_building_id(p)
            if bldg is not None:
                if is_friendly_turret(self.rc, p):
                    has_turret = True
                    break
                continue

            if is_pos_turretable(self.rc, p) and is_adjacent_with_diag(p, self.rc.get_position()):
                free_pos = p
                best_dir = d

        if has_turret: return (False, None, Direction.CENTRE)
        
        if free_pos is not None:
            
            if self.enemy_core_pos is not None and pos.distance_squared(self.enemy_core_pos) < GameConstants.SENTINEL_VISION_RADIUS_SQ:
                dir = free_pos.direction_to(self.enemy_core_pos)
            else:
                temp_enemy_core_pos = get_symmetric(self.core_pos, self.rc.get_map_width(), self.rc.get_map_height(), sense.sense_state.symmetries_possible[0])
                dir = free_pos.direction_to(temp_enemy_core_pos)
                # dir = pos.direction_to(free_pos).rotate_left().opposite()
            if dir == best_dir.opposite(): dir = dir.rotate_left()
            return (True, free_pos, dir)
        
        return (False, None, Direction.CENTRE)

    def is_launcher_protected(self, pos: Position) -> bool:
        not_enough_info = False
        for d in DIRECTIONS:
            p = pos.add(d)
            if not is_in_map(p, self.rc.get_map_width(), self.rc.get_map_height()): continue
            if not self.rc.is_in_vision(p):
                not_enough_info = True
                continue
            bldg = self.rc.get_tile_building_id(p)
            if bldg is None: continue
            entt = self.rc.get_entity_type(bldg)
            if entt == EntityType.LAUNCHER: return True

        return not_enough_info
        
    # def ore_is_hijacked(self, pos: Position) -> (bool, Direction):
    #     if pos is None: return (False, Direction.CENTRE)
    #     if not self.rc.is_in_vision(pos): return (False, Direction.CENTRE)
        
    #     has_harvester = get_building_type(self.rc, pos) == EntityType.HARVESTER
    #     if not has_harvester: return (False, Direction.CENTRE)
        # for d in CARDINAL_DIRECTIONS:
