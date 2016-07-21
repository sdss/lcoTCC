from __future__ import division, absolute_import
import os
import subprocess

__all__ = ["aph"]


def aph(tccActor, userCmd):
    """adjust collimation parameters
    """
    tccDir = os.getenv("TCC_DIR")
    killscript = os.path.join(tccDir, "bin/aph.sh")
    subprocess.call(killscript)
    userCmd.setState(userCmd.Done)

