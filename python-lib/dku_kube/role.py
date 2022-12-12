import logging, os, subprocess

from dku_utils.access import is_none_or_blank
from dku_google.gcloud import get_account

def create_admin_binding(user_name=None, kube_config_path=None):
    if is_none_or_blank(user_name):
        user_name = get_account()
    
    env = os.environ.copy()
    if not is_none_or_blank(kube_config_path):
        env['KUBECONFIG'] = kube_config_path
    logging.info("Checking clusterrolebinding with KUBECONFIG=%s" % kube_config_path)
    out = subprocess.check_output(["kubectl", "get", "clusterrolebinding", "cluster-admin-binding", "--ignore-not-found"], env=env)
    if not is_none_or_blank(out):
        logging.info("Clusterrolebinding already exist")
    else:
        subprocess.check_call(["kubectl", "create", "clusterrolebinding", "cluster-admin-binding", "--clusterrole", "cluster-admin", "--user", user_name], env=env)
