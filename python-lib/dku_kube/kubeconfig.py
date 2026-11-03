import os, sys, json, yaml, logging, subprocess
from dku_utils.access import _has_not_blank_property, _is_none_or_blank
try:
    from urllib.parse import urlsplit
except ImportError:
    from urlparse import urlsplit


def configure_control_plane_proxy(kube_config_path, bypass_proxy=False):
    """Optionally bypass an environment proxy for the selected control plane."""
    if not bypass_proxy or not any(os.environ.get(key, '').strip() for key in
                                 ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy")):
        return
    if not kube_config_path:
        logging.warning("Cannot configure control-plane proxy bypass: no kubeconfig path; keeping existing proxy settings")
        return

    try:
        config = json.loads(subprocess.check_output([
            "kubectl", "--kubeconfig", kube_config_path,
            "config", "view", "--minify", "-o", "json",
        ], universal_newlines=True, stderr=subprocess.PIPE))
        clusters = config.get("clusters") or []
        if len(clusters) != 1:
            logging.warning("Cannot configure control-plane proxy bypass: kubeconfig has no selected cluster; keeping existing proxy settings")
            return
        cluster = clusters[0].get("cluster", {})
        if cluster.get("proxy-url"):
            logging.info("Skipping control-plane proxy bypass: preserving explicit kubeconfig proxy-url")
            return
        server = urlsplit(cluster.get("server", ""))
        if server.scheme not in ("http", "https") or not server.hostname:
            logging.warning("Cannot configure control-plane proxy bypass: selected cluster has no valid server URL; keeping existing proxy settings")
            return
    except (OSError, subprocess.CalledProcessError, ValueError) as e:
        logging.warning("Cannot configure control-plane proxy bypass; keeping existing proxy settings: %s", e)
        return

    if not any(os.environ.get(key, '').strip() for key in
               (server.scheme.upper() + "_PROXY", server.scheme + "_proxy")):
        return

    hosts = [
        host.strip()
        for key in ("no_proxy", "NO_PROXY")
        for host in os.environ.get(key, "").split(",")
        if host.strip()
    ]
    if server.hostname not in hosts:
        hosts.append(server.hostname)
    no_proxy = "*" if "*" in hosts else ",".join(hosts)
    os.environ["NO_PROXY"] = no_proxy
    os.environ["no_proxy"] = no_proxy
    logging.info("Configured proxy bypass for control-plane host %s", server.hostname)

def get_first_kube_config(kube_config_path=None):
    if kube_config_path is None:
        if _has_not_blank_property(os.environ, 'KUBECONFIG'):
            kube_config_path = os.environ['KUBECONFIG'].split(':')[0]
        else:
            kube_config_path = os.path.join(os.environ['HOME'], '.kube', 'config')
    return kube_config_path

def merge_or_write_config(config, kube_config_path=None):
    kube_config_path = get_first_kube_config(kube_config_path)
    
    if os.path.exists(kube_config_path):
        logging.info("A kube config exists at %s => merging" % kube_config_path)
        with open(kube_config_path, "r") as f:
            existing = yaml.safe_load(f)
        for k in ['users', 'clusters', 'contexts']:
            elements = existing.get(k, [])
            existing[k] = elements
            new_elements = config.get(k, [])
            for new_element in new_elements:
                name = new_element.get("name", "")
                element_idx = None
                for i in range(0, len(elements)):
                    if elements[i].get("name", None) == name:
                        element_idx = i
                logging.info("  %s > %s : %s" % (k, name, 'replace' if element_idx is not None else 'append'))
                if element_idx is not None:
                    elements[element_idx] = new_element
                else:
                    elements.append(new_element)
        """
        if len(config.get("current-context", "")) > 0:
            current_context = config.get("current-context")
            logging.info("Setting current context to %s" % current_context)
            existing["current-context"] = current_context
        """
        
        logging.info("Final state is %s" % json.dumps(existing, indent=2))
            
        with open(kube_config_path, "w") as f:
            yaml.safe_dump(existing, f)
    else:
        logging.info("No kube config file found at %s => writing" % kube_config_path)

        with open(kube_config_path, "w") as f:
            yaml.safe_dump(config, f)
