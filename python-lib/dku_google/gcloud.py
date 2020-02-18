import os, sys, json, yaml, subprocess, logging
import socket
from dku_utils.access import _safe_get_value

GCLOUD_INFO = None
def _get_gcloud_info():
    global GCLOUD_INFO
    if GCLOUD_INFO is None:
        logging.info("Retrieving gcloud info")
        try:
            gcloud_info_str = subprocess.check_output(["gcloud", "info", "--format", "json"])
            GCLOUD_INFO = json.loads(gcloud_info_str)
        except:
            raise ValueError("gcloud CLI not found, check if Google Cloud SDK is properly installed and configured.")
    return GCLOUD_INFO


def get_sdk_root():
    sdk_root = _safe_get_value(_get_gcloud_info(), ["installation", "sdk_root"], None)
    return sdk_root


def get_access_token_and_expiry(config={}):
    logging.info("Retrieving gcloud access token and expiry")
    cmd_path = config.get("cmd-path", os.path.join(get_sdk_root(), "bin", "gcloud"))
    cmd_args = config.get("cmd-args", "config config-helper --format=json")
    info_str = subprocess.check_output("%s %s" % (cmd_path, cmd_args), shell=True)
    info = json.loads(info_str)
    token_key_chunks = config.get("token-key", "{.credential.access_token}")[2:-1].split('.')
    expiry_key_chunks = config.get("expiry-key", "{.credential.token_expiry}")[2:-1].split('.')
    return _safe_get_value(info, token_key_chunks), _safe_get_value(info, expiry_key_chunks)


def get_account():
    account = _safe_get_value(_get_gcloud_info(), ["config", "account"], None)
    return account


def _run_cmd(cmd=None):
    """
    Run command via subprocess. Clean retrieval of error message if fails. Trims any trailing space.
    """

    try:
        out = subprocess.check_output(cmd).rstrip()
    except subprocess.CalledProcessError as e:
        print(e.output)
    return out


def get_project_region_and_zone():
    """
    Call the 'gcloud config get-value' command to retrieve parameters.
    Requires that the gcloud CLI has been properly configured.
    """

    cmd = ["gcloud", "config", "get-value"]
    project = _run_cmd(cmd+["core/project"])
    region = _run_cmd(cmd+["compute/region"])
    zone = _run_cmd(cmd+["compute/zone"])

    logging.info("The following config params were found for gcloud: PROJECT={}, REGION={}, ZONE={}".format(project, region, zone))

    return project, region, zone


def _get_gce_instance_info():
    """
    Run 'gcloud compute instances describe <the-host-vm>'
    Requires the compute.zones.list IAM permission.
    """
    
    gce_instance_info = {}

    project, region, zone = get_project_region_and_zone()
    logging.info("Retrieving GCE VM info")
    cmd_base = ["gcloud", "compute", "instances", "describe"]
    gce_vm_name = socket.gethostname()
    cmd_base += [gce_vm_name]

    cmd_opts = ["--project", project, "--zone", zone]
    cmd_base += cmd_opts

    cmd_output_format = ["--format", "json"]
    cmd_base += cmd_output_format
    
    logging.info("Running CMD {}".format(cmd_base))
    gce_instance_info_str = _run_cmd(cmd_base)
    gce_instance_info = json.loads(gce_instance_info_str)

    return gce_instance_info


def get_gce_network():
    """
    Retrieve the network & subnetwork from the DSS host.
    """

    gce_instance_info = _get_gce_instance_info()
    network_interfaces = gce_instance_info["networkInterfaces"]
    default_nic = network_interfaces[0]
    if len(network_interfaces) > 1:
        logging.info("WARNING! Multiple network interfaces detected, will use {}".format(default_nic))
    network = default_nic["network"]
    subnetwork = default_nic["subnetwork"]

    return network, subnetwork


def get_gce_labels():
    """
    Retrieve the labels from the DSS host.
    """

    labels = _safe_get_value(_get_gce_instance_info(), "labels")
    return labels


def get_gce_service_account():
    """
    Retrieve the active service account on the DSS host
    """

    logging.info("Retrieving gcloud auth info")
    cmd_base = ["gcloud", "auth", "list"]
    cmd_output_format = ["--format", "json"]
    cmd_base += cmd_output_format

    try:
        gce_auth_info_str = subprocess.check_output(cmd_base)
    except subprocess.CalledProcessError as e:
        print(e.output)
    gce_auth_info = json.loads(gce_auth_info_str)
    for identity in gce_auth_info:
        if identity["status"] == "ACTIVE":
            gce_active_sa = identity["account"]
    logging.info("Active service account on DSS host is {}".format(gce_active_sa))
    return gce_active_sa
