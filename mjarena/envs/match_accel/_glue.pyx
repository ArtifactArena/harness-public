# cython: language_level=3, annotation_typing=False, infer_types=False
import numpy as np
from mjarena.agents.types import BotObservation
from mjarena.envs.occupancy_grid import build_arena_grid, build_arena_mass_grid

def build_bot_observation(self, for_red: bool, time_step: int) -> BotObservation:
    """Build full 3D observation for a bot.

    Args:
        for_red: If True, build observation from red's perspective
        time_step: Current timestep
    """
    my_bot = self.bot_red if for_red else self.bot_blue
    opp_bot = self.bot_blue if for_red else self.bot_red
    my_prefix = my_bot.prefix
    no_opponent = bool(self.game_context.get("__stage2x_no_opponent__"))
    opp_prefix = opp_bot.prefix

    detail = self.env.detailed_observations.for_robot(my_prefix)
    detail["elapsed_time"] = time_step * detail["control_dt"]
    detail["time_remaining"] = max(0, self.max_steps - time_step) * detail["control_dt"]
    my_state, opp_state = detail["my_robot"], detail["opponent_robot"]
    my_root = my_state["bodies"][my_state["root_body"]]
    opp_root = opp_state["bodies"][opp_state["root_body"]]
    snapshot = self.env.detailed_observations.data
    my_matrix = np.asarray(snapshot.xmat[self.env._root_body_ids[my_prefix]]).reshape(3, 3)
    opp_matrix = np.asarray(snapshot.xmat[self.env._root_body_ids[opp_prefix]]).reshape(3, 3)
    my_position = my_state["com_position"]
    opp_position = opp_state["com_position"]

    my_edge = self.env.closest_distance_to_boundary(my_position)
    opp_edge = self.env.closest_distance_to_boundary(opp_position)

    # Contact info
    opp_contact, opp_force, gnd_contact = self.env.get_contact_info(my_prefix)

    my_pos_arr = np.array(my_position, dtype=np.float32)
    opp_pos_arr = np.array(opp_position, dtype=np.float32)
    my_br = float(my_bot.bounding_radius)
    opp_br = float(opp_bot.bounding_radius)
    my_mass = float(my_bot.total_mass)
    opp_mass = float(opp_bot.total_mass)
    ring_r = float(getattr(self.env, 'ring_radius', 5.0))

    if no_opponent:
        opp_pos_arr = np.array([1e6, 1e6, 0.0], dtype=np.float32)
        opp_edge = 1e6
        opp_contact = False
        opp_force = 0.0
        opp_br = 0.0
        opp_mass = 0.0

    # Build spatial grids if enabled
    obs_cfg = self._obs_cfg
    gc = self._grid_cache

    arena_grid = None
    arena_mass_grid = None
    edge_dist_grid = None

    if gc is not None:
        if obs_cfg.arena_grid:
            arena_grid = build_arena_grid(gc, my_pos_arr, opp_pos_arr, my_br, opp_br)
        if obs_cfg.arena_mass_grid:
            arena_mass_grid = build_arena_mass_grid(
                gc, my_pos_arr, opp_pos_arr, my_br, opp_br, my_mass, opp_mass,
            )
        if obs_cfg.edge_distance_grid:
            edge_dist_grid = gc.edge_distance_grid

    return BotObservation(
        details=detail,
        # Position
        my_pos=my_pos_arr,
        opponent_pos=opp_pos_arr,
        # Orientation
        my_yaw=float(np.arctan2(my_matrix[1, 0], my_matrix[0, 0])),
        my_pitch=float(np.arcsin(np.clip(-my_matrix[2, 0], -1, 1))),
        my_roll=float(np.arctan2(my_matrix[2, 1], my_matrix[2, 2])),
        opponent_yaw=0.0 if no_opponent else float(np.arctan2(opp_matrix[1, 0], opp_matrix[0, 0])),
        opponent_pitch=0.0 if no_opponent else float(np.arcsin(np.clip(-opp_matrix[2, 0], -1, 1))),
        opponent_roll=0.0 if no_opponent else float(np.arctan2(opp_matrix[2, 1], opp_matrix[2, 2])),
        # Velocity
        my_velocity=np.array(my_root["linear_velocity"], dtype=np.float32),
        my_angular_velocity=np.array(my_matrix.T @ my_root["angular_velocity"], dtype=np.float32),
        opponent_velocity=(
            np.zeros(3, dtype=np.float32)
            if no_opponent
            else np.array(opp_root["linear_velocity"], dtype=np.float32)
        ),
        opponent_angular_velocity=(
            np.zeros(3, dtype=np.float32)
            if no_opponent
            else np.array(opp_matrix.T @ opp_root["angular_velocity"], dtype=np.float32)
        ),
        my_actuator_velocity=my_bot.actuator_joint_velocity(snapshot),
        opponent_actuator_velocity=(
            np.zeros(0, dtype=np.float32)
            if no_opponent
            else opp_bot.actuator_joint_velocity(snapshot)
        ),
        # Distances
        distance_to_opponent=(
            1e6 if no_opponent else float(np.linalg.norm(my_position - opp_position))
        ),
        my_edge_distance=float(my_edge),
        opponent_edge_distance=float(opp_edge),
        # Contact
        opponent_contact=bool(opp_contact),
        opponent_contact_force=float(opp_force),
        ground_contact=bool(gnd_contact),
        # Stability
        is_tipping=float(np.clip(np.arccos(np.clip(my_matrix[2, 2], -1, 1)) / (np.pi / 2), 0, 1)),
        # Time
        t=int(time_step),
        max_t=int(self.max_steps),
        game={
            str(k): v
            for k, v in self.game_context.items()
            if not str(k).startswith("__")
        },
        # Robot properties
        my_bounding_radius=my_br,
        opponent_bounding_radius=opp_br,
        ring_radius=ring_r,
        # Spatial grids
        arena_grid=arena_grid,
        arena_mass_grid=arena_mass_grid,
        edge_distance_grid=edge_dist_grid,
        # Inactivity timers
        my_inactivity_timer=getattr(self.env, '_inactivity_timers', {"red": 0.0, "blue": 0.0}).get("red" if for_red else "blue", 0.0),
        opponent_inactivity_timer=getattr(self.env, '_inactivity_timers', {"red": 0.0, "blue": 0.0}).get("blue" if for_red else "red", 0.0),
    )

SOURCE_HASHES={'mjarena/runner/episode.py': '99803b2c99768496157b681f11de7451a6e80f6f469fe0a9b24261c291052198'}
