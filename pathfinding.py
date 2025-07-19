import heapq
import typing
import math

from utils import HexCoord
from geometry import hex_distance

Graph = typing.Dict[str, typing.List[str]] # Adjacency list: system_name -> [connected_system_names]
Path = typing.List[str] # List of system names forming a path

def find_intersystem_path(graph: Graph, start_node: str, end_node: str) -> typing.Optional[Path]:
    """
    Finds the shortest path between two nodes in a graph (star systems in the galaxy) using Dijkstra's algorithm.
    Assumes all edge weights are 1 (i.e., finds the path with the fewest hops).

    Args:
        graph: The graph represented as an adjacency list.
        start_node: The starting system name.
        end_node: The target system name.

    Returns:
        A list of system names representing the shortest path from start_node to
        end_node, or None if no path exists.
    """
    if start_node not in graph or end_node not in graph:
        print(f"Warning: Start node '{start_node}' or end node '{end_node}' not in graph.")
        return None

    if start_node == end_node:
        return [start_node]

    # Distances from start_node to every other node
    # Initialize all distances to infinity, start_node to 0
    distances: typing.Dict[str, float] = {node: float('inf') for node in graph}
    distances[start_node] = 0

    # Predecessors: to reconstruct the path later
    # Stores node: predecessor_node
    predecessors: typing.Dict[str, typing.Optional[str]] = {node: None for node in graph}

    # Priority queue: (distance, node_name)
    # heapq implements a min-heap, so it's perfect for Dijkstra's
    priority_queue: typing.List[typing.Tuple[float, str]] = [(0, start_node)]

    while priority_queue:
        current_distance, current_node = heapq.heappop(priority_queue)

        # If we've already found a shorter path to current_node, skip
        if current_distance > distances[current_node]:
            continue

        # If we've reached the end_node, reconstruct and return the path
        if current_node == end_node:
            path: Path = []
            node_trace = end_node
            while node_trace is not None:
                path.append(node_trace)
                node_trace = predecessors[node_trace]
            return path[::-1] # Reverse to get start -> end order

        # Explore neighbors
        if current_node in graph: # Check if current_node has neighbors defined
            for neighbor in graph[current_node]:
                # Assuming edge weight is 1 for each jump
                distance_to_neighbor = current_distance + 1

                if distance_to_neighbor < distances[neighbor]:
                    distances[neighbor] = distance_to_neighbor
                    predecessors[neighbor] = current_node
                    heapq.heappush(priority_queue, (distance_to_neighbor, neighbor))
        else:
            # This case should ideally not happen if the graph is well-formed
            # (i.e., all nodes listed as neighbors also exist as keys in the graph)
            print(f"Warning: Node '{current_node}' found as neighbor but not as a key in the graph.")


    # If the loop finishes and end_node wasn't reached
    return None

# --- Hex Grid Pathfinding ---

def _axial_to_cube(hex_coord: HexCoord) -> typing.Tuple[float, float, float]:
    """Converts axial coordinates to cube coordinates."""
    q, r = hex_coord
    x = float(q)
    z = float(r)
    y = -x - z
    return (x, y, z)

def _cube_round(cube: typing.Tuple[float, float, float]) -> typing.Tuple[int, int, int]:
    """Rounds cube coordinates to the nearest integer cube coordinates, ensuring the sum is 0."""
    rx = round(cube[0])
    ry = round(cube[1])
    rz = round(cube[2])

    x_diff = abs(rx - cube[0])
    y_diff = abs(ry - cube[1])
    z_diff = abs(rz - cube[2])

    if x_diff > y_diff and x_diff > z_diff:
        rx = -ry - rz
    elif y_diff > z_diff:
        ry = -rx - rz
    else:
        rz = -rx - ry

    return (int(rx), int(ry), int(rz))

def _cube_to_axial(cube: typing.Tuple[float, float, float]) -> HexCoord:
    """Converts cube coordinates (potentially rounded) back to axial coordinates."""
    return (int(cube[0]), int(cube[2]))

def _cube_lerp(a: typing.Tuple[float, float, float], b: typing.Tuple[float, float, float], t: float) -> typing.Tuple[float, float, float]:
    """Linear interpolation for cube coordinates."""
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )

def find_hex_jump_path(start_hex: HexCoord, end_hex: HexCoord, max_range: int) -> typing.List[HexCoord]:
    """
    Calculates a list of waypoints for a jump between two hexes,
    ensuring no single jump exceeds the max_range.
    """
    print(f"  [find_hex_jump_path] Calculating multi-stage jump from {start_hex} to {end_hex} with max jump range {max_range}.")
    path: typing.List[HexCoord] = []
    total_distance = hex_distance(start_hex, end_hex)

    if total_distance <= max_range:
        print(f"  [find_hex_jump_path] Total distance {total_distance} is within max range. No waypoints needed.")
        return [end_hex]

    start_cube = _axial_to_cube(start_hex)
    end_cube = _axial_to_cube(end_hex)

    num_segments = math.ceil(total_distance / max_range)
    print(f"  [find_hex_jump_path] Calculated {num_segments} segments for the jump.")

    for i in range(1, int(num_segments) + 1):
        t = i / num_segments
        interpolated_cube = _cube_lerp(start_cube, end_cube, t)
        rounded_cube = _cube_round(interpolated_cube)
        waypoint_hex = _cube_to_axial(rounded_cube)
        
        if not path or path[-1] != waypoint_hex:
            path.append(waypoint_hex)
            
    # Ensure the final destination is exactly the end_hex, correcting for any rounding errors
    if not path or path[-1] != end_hex:
        if path and hex_distance(path[-1], end_hex) == 0:
             path[-1] = end_hex
        else:
             # This case is tricky, if the last waypoint is not the end_hex, we should just append it.
             # A more robust solution might check if the last waypoint overshot and replace it.
             # For now, we ensure the final destination is always included.
             path.append(end_hex)

    print(f"  [find_hex_jump_path] Final waypoints: {path}")
    return path
