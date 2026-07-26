import pet.utils as utils

config = utils.loadConfig()

WINDOW_TITLE = config["window"]["title"]
PET_WIDTH = config["window"]["size"]["width"]
PET_HEIGHT = config["window"]["size"]["height"]
COLLISION_OFFSET_LEFT = config["window"]["collision_offset"]["left"]
COLLISION_OFFSET_RIGHT = config["window"]["collision_offset"]["right"]
COLLISION_OFFSET_TOP = config["window"]["collision_offset"]["top"]
COLLISION_OFFSET_BOTTOM = config["window"]["collision_offset"]["bottom"]
STEP_SECONDS = config["window"]["physics"]["step_seconds"]
GRAVITY = config["window"]["physics"]["gravity"]
MAX_THROW_SPEED = config["window"]["physics"]["max_throw_speed"]
WALL_BOUNCE = config["window"]["physics"]["wall_bounce"]
