TIMEOPT_CONFIG_FILE = "cfg_softConstraints_hyq.yaml"
from .common_hyq import *
SCRIPT_PATH = "demos"
ENV_NAME = "multicontact/darpa"

DURATION_INIT = 1.5  # Time to init the motion
DURATION_FINAL = 1.5  # Time to stop the robot
DURATION_FINAL_SS = 1.
DURATION_SS = 0.8
DURATION_DS = 0.8
DURATION_TS = 0.8
DURATION_QS = 0.3

## Settings for end effectors :
EFF_T_PREDEF = 0.1
p_max = 0.2

## Override default settings :
#DISPLAY_INIT_GUESS_TRAJ = True
#USE_GEOM_INIT_GUESS = False
#USE_CROC_INIT_GUESS = True
#USE_CROC_COM = True
