TIMEOPT_CONFIG_FILE = "cfg_softConstraints_talos.yaml"
from .common_talos import *
SCRIPT_PATH = "demos"
ENV_NAME = "multicontact/bauzil_stairs"

DURATION_INIT = 1.5  # Time to init the motion
DURATION_FINAL = 1  # Time to stop the robot
DURATION_FINAL_SS = 1.
DURATION_SS = 1.4
DURATION_DS = 0.3
DURATION_TS = 0.4

EFF_T_PREDEF = 0.2
p_max = 0.13

GUIDE_STEP_SIZE = 0.8
MAX_SURFACE_AREA = 2.

COM_SHIFT_Z = -0.025
TIME_SHIFT_COM = 2.
