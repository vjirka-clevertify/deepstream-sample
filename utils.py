import time

vehicle_data = {}


def calculate_vehicle_speed(vehicle_id, position, timestamp):
    """
    Calculate the speed of a vehicle using its position and timestamp.

    Args:
        vehicle_id (int): Unique ID of the vehicle.
        position (tuple): (x, y) pixel position of the vehicle.
        timestamp (int): NTP timestamp of the frame (in nanoseconds).

    Returns:
        float: Speed in km/h.
    """
    if vehicle_id not in vehicle_data:
        vehicle_data[vehicle_id] = {"position": position, "timestamp": timestamp}
        return 0.0

    prev_data = vehicle_data[vehicle_id]
    distance = calculate_distance(prev_data["position"], position)
    time_diff = (timestamp - prev_data["timestamp"]) / 1e9

    vehicle_data[vehicle_id] = {"position": position, "timestamp": timestamp}

    if time_diff <= 0:
        return 0.0

    return (distance / time_diff) * 3.6


def calculate_distance(pos1, pos2):
    """
    Calculate the real-world distance between two positions.

    Args:
        pos1 (tuple): (x1, y1) position.
        pos2 (tuple): (x2, y2) position.

    Returns:
        float: Distance in meters.
    """
    pixel_distance = ((pos2[0] - pos1[0]) ** 2 + (pos2[1] - pos1[1]) ** 2) ** 0.5
    meters_per_pixel = 0.05
    return pixel_distance * meters_per_pixel


def cleanup_vehicle_data(max_age=10):
    """
    Remove outdated vehicle entries from the vehicle_data dictionary.

    Args:
        max_age (int): Maximum age of entries in seconds.
    """
    current_time = time.time()
    for vehicle_id in list(vehicle_data.keys()):
        if current_time - vehicle_data[vehicle_id]["timestamp"] > max_age:
            del vehicle_data[vehicle_id]
