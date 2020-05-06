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


def _run_cmd(cmd=None):
    """
    Run command via subprocess. Clean retrieval of error message if fails. Trims any trailing space.
    """

    logging.info("Running CMD {}".format(cmd))
    try:
        out = subprocess.check_output(cmd).rstrip()
    except subprocess.CalledProcessError as e:
        print(e.output)
    return out


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
    instance_info["region"] = zone.split("-")[:-1]
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
