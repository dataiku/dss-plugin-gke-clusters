import os
import logging
import subprocess

from dku_utils.access import _has_not_blank_property
from dku_utils.access import _is_none_or_blank

DAEMONSET_MANIFEST_URL = "https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nvidia-driver-installer/cos/daemonset-preloaded.yaml"

def create_installer_daemonset(kube_config_path=None):
    """
    Launch a pod on each node that will install the NVIDIA drivers.
    """

    env = os.environ.copy()
    if not _is_none_or_blank(kube_config_path):
        env["KUBECONFIG"] = kube_config_path
    logging.info("Starting NVIDIA driver installer daemonset with KUBECONFIG=%s" % kube_config_path)
    subprocess.check_call(["kubectl", "apply", "-f", DAEMONSET_MANIFEST_URL], env=env)