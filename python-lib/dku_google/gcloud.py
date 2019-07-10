import os, sys, json, yaml, subprocess, logging
from dku_utils.access import _safe_get_value

GCLOUD_INFO = None
def _get_gcloud_info():
    global GCLOUD_INFO
    if GCLOUD_INFO is None:
        logging.info("Retrieving gcloud info")
        gcloud_info_str = subprocess.check_output(["gcloud", "info", "--format", "json"])
        GCLOUD_INFO = json.loads(gcloud_info_str)
    return GCLOUD_INFO
    
def get_sdk_root():
    sdk_root = _safe_get_value(_get_gcloud_info(), ["installation", "sdk_root"], None)
    return sdk_root

def get_account():
    account = _safe_get_value(_get_gcloud_info(), ["config", "account"], None)
    return account

def get_project_region_and_zone():
    project = _safe_get_value(_get_gcloud_info(), ["config", "project"], None)
    region = _safe_get_value(_get_gcloud_info(), ["config", "properties", "compute", "region"], None)
    zone = _safe_get_value(_get_gcloud_info(), ["config", "properties", "compute", "zone"], None)
    return project, region, zone

def get_access_token_and_expiry(config={}):
    logging.info("Retrieving gcloud access token and expiry")
    cmd_path = config.get("cmd-path", os.path.join(get_sdk_root(), "bin", "gcloud"))
    cmd_args = config.get("cmd-args", "config config-helper --format=json")
    info_str = subprocess.check_output("%s %s" % (cmd_path, cmd_args), shell=True)
    info = json.loads(info_str)
    token_key_chunks = config.get("token-key", "{.credential.access_token}")[2:-1].split('.')
    expiry_key_chunks = config.get("expiry-key", "{.credential.token_expiry}")[2:-1].split('.')
    return _safe_get_value(info, token_key_chunks), _safe_get_value(info, expiry_key_chunks) 