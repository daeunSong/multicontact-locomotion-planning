from mlp.config import Config
import mlp.viewer.display_tools as display_tools
from mlp.viewer.display_tools import displayEffectorTrajectories
import os, sys, argparse
import eigenpy
import time
import pinocchio
import curves
import multicontact_api
from mlp.utils import plot
from mlp.utils.cs_tools import copyEffectorTrajectories
from mlp.utils import check_path
from mlp.export import blender, gazebo, npz, openHRP, sotTalosBalance
eigenpy.switchToNumpyArray()

try:
    #python2
    input = raw_input
except NameError:
    pass


class LocoPlanner:

    def __init__(self, cfg):
        self.cfg = cfg
        self.cs = None
        self.cs_initGuess = None
        self.cs_com = None
        self.cs_ref = None
        self.cs_wb = None
        self.fullBody = None
        self.viewer = None
        self.gui = None
        # arrays used to store the cs after each iterations of the dynamic filter
        self.cs_com_iters = []
        self.cs_ref_iters = []
        self.cs_wb_iters = []
        self.motion_valid = None

    def run_contact_generation(self):
        print("### MLP : contact sequence ###")
        import mlp.contact_sequence as contactGeneration
        self.cs, self.fullBody, self.viewer = contactGeneration.generateContactSequence(self.cfg)
        contactGeneration.Outputs.assertRequirements(self.cs)
        self.gui = self.viewer.client.gui

        if self.cfg.WRITE_STATUS:
            with open(self.cfg.STATUS_FILENAME, "a") as f:
                f = open(cfg.STATUS_FILENAME, "a")
                f.write("gen_cs_success: True\n")

        if self.cfg.DISPLAY_CS_STONES:
            display_tools.displaySteppingStones(self.cs, self.gui, self.viewer.sceneName, self.cfg.Robot)
        if self.cfg.DISPLAY_CS:
            if display_tools.DisplayContactSequenceRequirements.checkAndFillRequirements(self.cs, self.cfg, self.fullBody):
                input("Press Enter to display the contact sequence ...")
                display_tools.displayContactSequence(self.viewer, self.cs)

    def run_centroidal_init_guess(self):
        print("------------------------------")
        print("### MLP : centroidal, initial Guess ###")
        import mlp.centroidal.initGuess as centroidalInitGuess
        if not centroidalInitGuess.Inputs.checkAndFillRequirements(self.cs, self.cfg, self.fullBody):
            raise RuntimeError(
                "The current contact sequence cannot be given as input to the centroidalInitGuess method selected.")
        self.cs_initGuess = centroidalInitGuess.generateCentroidalTrajectory(self.cfg, self.cs,
                                                                             fullBody=self.fullBody,
                                                                             viewer=self.viewer)
        centroidalInitGuess.Outputs.assertRequirements(self.cs_initGuess)

        if cfg.DISPLAY_INIT_GUESS_TRAJ and self.cs_initGuess:
            colors = [self.viewer.color.red, self.viewer.color.yellow]
            display_tools.displayCOMTrajectory(self.cs_initGuess, self.gui, self.viewer.sceneName, self.cfg.SOLVER_DT, colors, "_init")

    def run_centroidal(self, iter_dynamic_filter = 0):
        print("------------------------------")
        print("### MLP : centroidal  ###")
        import mlp.centroidal as centroidal
        if not centroidal.Inputs.checkAndFillRequirements(self.cs, self.cfg, self.fullBody):
            raise RuntimeError(
                "The current contact sequence cannot be given as input to the centroidal method selected.")
        if iter_dynamic_filter > 0:
            if self.cs_wb is not None:
                self.cs_initGuess = self.cs_wb
        self.cs_com = centroidal.generateCentroidalTrajectory(self.cfg, self.cs, self.cs_initGuess,
                                                             self.fullBody, self.viewer,
                                                             iter_dynamic_filter == 0)
        centroidal.Outputs.assertRequirements(self.cs_com)
        self.cs_com_iters += [self.cs_com]

        if cfg.WRITE_STATUS and iter_dynamic_filter == 0:
            with open(self.cfg.STATUS_FILENAME, "a") as f:
                f.write("centroidal_success: True\n")

        if cfg.DISPLAY_COM_TRAJ:
            colors = [self.viewer.color.blue, self.viewer.color.green]
            display_tools.displayCOMTrajectory(self.cs_com, self.gui, self.viewer.sceneName, cfg.DT_DISPLAY, colors)
        if cfg.PLOT_CENTROIDAL:
            plot.plotCOMTraj(self.cs_com, self.cfg.SOLVER_DT, " - iter " + str(iter_dynamic_filter))
            plot.plotAMTraj(self.cs_com, self.cfg.SOLVER_DT, " - iter " + str(iter_dynamic_filter))
            plot.plt.show(block=False)

    def run_effector_init_guess(self):
        print("------------------------------")
        print("### MLP : End effector initial Guess  ###")
        if self.cs_ref is not None and self.cs_ref.haveEffectorsTrajectories(1e-2):
            print("Try to copy from previous iteration.")
            self.cs_ref = copyEffectorTrajectories(self.cs_ref, self.cs_com)
        if self.cs_ref is None:
            import mlp.end_effector.initGuess as effectorsInitGuess
            if not effectorsInitGuess.Inputs.checkAndFillRequirements(self.cs_com, self.cfg, self.fullBody):
                raise RuntimeError(
                    "The current contact sequence cannot be given as input to the end effector method selected.")
            self.cs_ref = effectorsInitGuess.generateEffectorTrajectoriesForSequence(self.cfg, self.cs_com, self.fullBody)
            effectorsInitGuess.Outputs.assertRequirements(self.cs_ref)
        self.cs_ref_iters += [self.cs_ref]

        if cfg.DISPLAY_ALL_FEET_TRAJ:
            displayEffectorTrajectories(self.cs_ref, self.viewer, self.fullBody, "_ref", 0.6)

    def run_wholebody(self, iter_dynamic_filter = 0):
        print("------------------------------")
        print("### MLP : whole-body  ###")
        import mlp.wholebody as wholeBody
        if not wholeBody.Inputs.checkAndFillRequirements(self.cs_ref, self.cfg, self.fullBody):
            raise RuntimeError(
                "The current contact sequence cannot be given as input to the wholeBody method selected.")
        if iter_dynamic_filter > 0:
            self.cfg.IK_trackAM = False
            self.cfg.w_am = self.cfg.w_am_track
            self.cfg.kp_am = self.cfg.kp_am_track

        self.cs_wb = wholeBody.generateWholeBodyMotion(self.cfg, self.cs_ref, self.fullBody, self.viewer)
        wholeBody.Outputs.assertRequirements(self.cs_wb)
        self.cs_wb_iters += [self.cs_wb]

        if cfg.WRITE_STATUS and iter_dynamic_filter == 0:
            if not os.path.exists(cfg.OUTPUT_DIR):
                os.makedirs(cfg.OUTPUT_DIR)
            with open(self.cfg.STATUS_FILENAME, "a") as f:
                f.write("wholebody_success: True\n")
                if self.cs_wb.size() == self.cs_ref.size():
                    f.write("wholebody_reach_goal: True\n")
                else:
                    f.write("wholebody_reach_goal: False\n")

    def finish_solve(self):
        if self.cfg.DISPLAY_FEET_TRAJ:
            if cfg.IK_store_effector:
                displayEffectorTrajectories(self.cs_wb, self.viewer, self.fullBody)
            else:
                displayEffectorTrajectories(self.cs_ref, self.viewer, self.fullBody)

        if self.cfg.CHECK_FINAL_MOTION and self.cs_wb is not None and self.cs_wb.size() > 0:
            print("## Begin validation of the final motion (collision and joint-limits)")
            validator = check_path.PathChecker(self.fullBody, self.cfg.CHECK_DT, True)
            motion_valid, t_invalid = validator.check_motion(self.cs_wb.concatenateQtrajectories())
            print("## Check final motion, valid = ", motion_valid)
            if not motion_valid:
                print("## First invalid time : ", t_invalid)
            if self.cfg.WRITE_STATUS:
                with open(self.cfg.STATUS_FILENAME, "a") as f:
                    f.write("motion_valid: " + str(motion_valid) + "\n")
        elif self.cs_wb is not None and self.cs_wb.size() > 0:
            self.motion_valid = True
        else:
            self.motion_valid = False

        if self.cfg.DISPLAY_WB_MOTION:
            input("Press Enter to display the whole body motion ...")
            display_tools.displayWBmotion(self.viewer, self.cs_wb.concatenateQtrajectories(), self.cfg.DT_DISPLAY)

        if self.cfg.PLOT:
            plot.plotALLFromWB(self.cs_ref_iters, self.cs_wb_iters, self.cfg)
            if self.cfg.ITER_DYNAMIC_FILTER > 0:
                plot.compareCentroidal(self.cs, self.cs_com_iters, self.cfg)

    def export_all(self):
        cfg = self.cfg
        if cfg.SAVE_CS:
            if not os.path.exists(cfg.CONTACT_SEQUENCE_PATH):
                os.makedirs(cfg.CONTACT_SEQUENCE_PATH)
            filename = cfg.CS_FILENAME
            print("Write contact sequence binary file : ", filename)
            self.cs.saveAsBinary(filename)
        if cfg.SAVE_CS_COM:
            if not os.path.exists(cfg.CONTACT_SEQUENCE_PATH):
                os.makedirs(cfg.CONTACT_SEQUENCE_PATH)
            filename = cfg.COM_FILENAME
            print("Write contact sequence binary file with centroidal trajectory : ", filename)
            self.cs_com.saveAsBinary(filename)
        if cfg.SAVE_CS_REF:
            if not os.path.exists(cfg.CONTACT_SEQUENCE_PATH):
                os.makedirs(cfg.CONTACT_SEQUENCE_PATH)
            filename = cfg.REF_FILENAME
            print("Write contact sequence binary file with centroidal and end effector trajectories: ", filename)
            self.cs_ref.saveAsBinary(filename)
        if cfg.SAVE_CS_WB:
            if not os.path.exists(cfg.CONTACT_SEQUENCE_PATH):
                os.makedirs(cfg.CONTACT_SEQUENCE_PATH)
            filename = cfg.WB_FILENAME
            print("Write contact sequence binary file with wholebody trajectories: ", filename)
            self.cs_wb.saveAsBinary(filename)

        if cfg.EXPORT_OPENHRP and self.motion_valid:
            openHRP.export(self.cfg, self.cs_com, self.cs_wb)  # FIXME
        if cfg.EXPORT_GAZEBO and self.motion_valid:
            gazebo.export(self.cfg, self.cs_wb.concatenateQtrajectories())
        if cfg.EXPORT_NPZ and self.motion_valid:
            npz.export(self.cfg, self.cs_ref, self.cs_wb, cfg)
        if cfg.EXPORT_BLENDER:
            blender.export(self.cfg, self.cs_wb.concatenateQtrajectories(), self.viewer)
            blender.exportSteppingStones(self.viewer)
        if cfg.EXPORT_SOT:
            sotTalosBalance.export(self.cfg, self.cs_wb)  # FIXME

    def display_cs(self, step=0.2):
        display_tools.displayContactSequence(self.viewer, self.cs, step)

    def display_wb(self, t=None):
        if t is None:
            display_tools.displayWBmotion(self.viewer, self.cs_wb.concatenateQtrajectories(), self.cfg.DT_DISPLAY)
        else:
            display_tools.displayWBatT(self.viewer, self.cs_wb, t)

    def run(self):

        t_start = time.time()
        self.run_contact_generation()
        self.run_centroidal_init_guess()

        for iter_dynamic_filter in range(self.cfg.ITER_DYNAMIC_FILTER + 1):
            if iter_dynamic_filter > 0:
                print("\n########################################")
                print("#### Iter " + str(iter_dynamic_filter) + " of the dynamic filter.  #### ")
                print("######################################## \n")
            self.run_centroidal(iter_dynamic_filter)
            self.run_effector_init_guess()
            self.run_wholebody(iter_dynamic_filter)

        t_total = time.time() - t_start
        print("### Complete motion generation time: " + str(t_total) + " s")

        self.finish_solve()
        self.export_all()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="todo")
    parser.add_argument('demo_name', type=str, help="The name of the demo configuration file to load. "
                                                    "Must be a valid python file, either inside the PYTHONPATH"
                                                    "or inside the mlp.demo_configs folder. ")
    args = parser.parse_args()
    demo_name = args.demo_name

    cfg = Config()
    cfg.load_scenario_config(demo_name)

    loco_planner = LocoPlanner(cfg)
    loco_planner.run()


"""
if len(sys.argv) < 2:
    print(
        "## WARNING : script called without specifying a demo config file (one of the file contained in mlp.demo_config)"
    )
    print("## Available demo files : ")
    configs_path = cfg.PKG_PATH + "/scripts/mlp/demo_configs"
    demos_list = os.listdir(configs_path)
    for f in demos_list:
        if f.endswith(".py") and not f.startswith("__") and not f.startswith("common"):
            print(f.rstrip(".py"))
    print("## Some data will be missing, scripts may fails. (cfg.Robot will not exist)")
    
"""

"""
#record gepetto-viewer 
viewer.startCapture("capture/capture","png")
dispWB()
viewer.stopCapture()
"""
