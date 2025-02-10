import os, sys, json, yaml, subprocess, logging
import socket
import requests

from dku_utils.access import _safe_get_value

GCLOUD_INFO = None
METADATA_SERVER_BASE_URL="http://metadata/computeMetadata/v1/"

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


def _run_cmd(cmd=None, **kwargs):
    """
    Run command via subprocess. Clean retrieval and throw of error message if fails. Trims any trailing space.
    """

    cmd_pretty = ' '.join(cmd)
    logging.info("Running CMD: {}".format(cmd_pretty))
    p = subprocess.Popen(cmd,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         universal_newlines=True,
                         **kwargs)
    out, err = p.communicate()
    rv = p.wait()
    if rv != 0:
        raise Exception(err)

    cmd_out = out.rstrip()
    logging.debug("'{}' output: {}".format(cmd_pretty, cmd_out))
    return cmd_out


def get_instance_info():
    """
    Retrieve the instance name, project, region and zone by calling the local
    metadata server.
    """

    metadata_flavor = {"Metadata-Flavor": "Google"}
    instance_info = {}
    instance_info["project"] = requests.get("/".join([METADATA_SERVER_BASE_URL,
                                                      "project",
                                                      "project-id"]),
                                            headers=metadata_flavor).text
    zone_full = requests.get("/".join([METADATA_SERVER_BASE_URL,
                                       "instance",
                                       "zone"]),
                        headers=metadata_flavor).text
    zone = zone_full.split("/")[-1] 
    instance_info["zone"] = zone
    instance_info["region"] = '-'.join(zone.split("-")[:-1])
    instance_info["vm_name"] = requests.get("/".join([METADATA_SERVER_BASE_URL,
                                                      "instance",
                                                      "name"]),
                                            headers=metadata_flavor).text
    return instance_info


def get_instance_network():
    """
    Retrieve the network and subnetwork of the DSS host.
    """

    instance_info = get_instance_info()
    cmd = ["gcloud", "compute", "instances", "describe"]
    cmd += [
                    instance_info["vm_name"],
                    "--project",
                    instance_info["project"],
                    "--zone",
                    instance_info["zone"],
                    "--format=json"
                ]   
    instance_full_info = json.loads(_run_cmd(cmd))
    network_interfaces = instance_full_info["networkInterfaces"]
    default_nic = network_interfaces[0]
    if len(network_interfaces) > 1:
        logging.info("WARNING! Multiple NICs detected, will use {}".format(default_nic))
    network = default_nic["network"]
    subnetwork = default_nic["subnetwork"]
    return network, subnetwork


def get_instance_service_account():
    """
    Retrieve the active service account of the DSS host
    """

    logging.info("Retrieving gcloud auth info")
    cmd = ["gcloud", "auth", "list", "--format=json"]
    instance_auth_info = json.loads(_run_cmd(cmd))
    for identity in instance_auth_info:
        if identity["status"] == "ACTIVE":
            instance_active_sa = identity["account"]
    logging.info("Active service account on DSS host is {}".format(instance_active_sa))
    return instance_active_sa


def create_kube_config_file(project_id, cluster_id, is_cluster_regional, region_or_zone, kube_config_path):
    """
    Delegate the creation of the kube config file to gke-gcloud-auth-plugin
    Starting with Kubernetes 1.26, the authentication to execute kubectl commands on Google clusters
        won't be available in kubectl anymore and the client go auth plugin needs to be used
    The gke-gcloud-auth-plugin is installed on the machine directly from the image
    It will keep an authentication token linked to the unix user on the machine for gcloud and kubectl calls
    Command `gcloud container clusters get-credentials CLUSTER_NAME` configures the authentication
        for the specified cluster, and creates an adequate kubeconfig file.
    """

    # Deleting the kube config for this cluster if it already exists
    logging.info("Checking if a kube config file already exists")
    if os.path.isfile(kube_config_path):
        logging.info("Deleting existing kube config file: {}".format(kube_config_path))
        os.remove(kube_config_path)
    
    # Configure the environment variables to use gcloud command
    logging.info("Running command to activate gcloud auth plugin for cluster {}".format(cluster_id))
    gcloud_env = os.environ.copy()
    # Use the new client go auth plugin authentication mode
    gcloud_env["USE_GKE_GCLOUD_AUTH_PLUGIN"] = "True"
    # Provide the desired location for the kube config to override the default value used by the auth plugin
    gcloud_env["KUBECONFIG"] = kube_config_path

    # Build the command
    cmd = ["gcloud", "container", "clusters", "get-credentials", cluster_id]
    
    if project_id is not None and len(project_id) > 0:
        cmd.append("--project")
        cmd.append(project_id)
        
    if is_cluster_regional:
        cmd.append("--region")
        cmd.append(region_or_zone)
    else:
        cmd.append("--zone")
        cmd.append(region_or_zone)
    
    # Run the command
    _run_cmd(cmd, env=gcloud_env)
