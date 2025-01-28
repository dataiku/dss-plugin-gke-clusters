import os
import logging
import subprocess
from dku_utils.access import _is_none_or_blank
from dku_utils.static_resources import download_to_disk, get_static_resource_path
from dku_kube.kubectl_command import run_with_timeout

DAEMONSET_MANIFEST_URL = "https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nvidia-driver-installer/cos/daemonset-preloaded.yaml"

def has_installer_daemonset(kube_config_path=None):
    env = os.environ.copy()
    if not _is_none_or_blank(kube_config_path):
        logging.info("Setting kube_config path from KUBECONFIG env variable...")
        env["KUBECONFIG"] = kube_config_path
        logging.info("Found KUBECONFIG={}".format(env["KUBECONFIG"]))

    out, err = run_with_timeout(["kubectl", "get", "daemonset", "nvidia-driver-installer", "-n", "kube-system", "--ignore-not-found"], env=env, timeout=5)
    return len(out.strip()) > 0

def create_installer_daemonset_if_needed(kube_config_path=None):
    """
    Launch a pod on each node that will install the NVIDIA drivers.
    """
    env = os.environ.copy()
    if not has_installer_daemonset(kube_config_path):
        if not _is_none_or_blank(kube_config_path):
            logging.info("Setting kube_config path from KUBECONFIG env variable...")
            env["KUBECONFIG"] = kube_config_path
            logging.info("Found KUBECONFIG={}".format(env["KUBECONFIG"]))

        logging.info("Creating NVIDIA driver daemonset (only GPU-tainted nodes will be affected)")
        daemonset_path = download_to_disk(DAEMONSET_MANIFEST_URL, download_location="daemonset-preloaded.yaml")

        if not daemonset_path:
            logging.warning("Unable to retrieve daemonset from '%s', using bundled definition instead.")
            daemonset_path = get_static_resource_path("daemonset-preloaded.yaml")
            if not os.path.exists(daemonset_path):
                logging.error("No bundled daemonset definition found at '%s'. GPU driver must be installed manually." % daemonset_path)
                return

        subprocess.check_call(["kubectl", "apply", "-f", daemonset_path], env=env)
    else:
        logging.info("NVIDIA driver daemonset already present on the cluster. Skipping.")