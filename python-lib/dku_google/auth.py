from google.oauth2 import service_account
import os, sys, json
import logging
import dataiku
import httplib2
from contextlib import contextmanager

def _log_get_credentials(credentials):
    if hasattr(credentials, 'service_account_email'):
        logging.info("Credentials loaded : %s" % credentials.service_account_email)
    else:
        logging.info("Credentials loaded")

def get_credentials_from_json_or_file(data):
    try:
        parsed = json.loads(data)
        credentials = service_account.Credentials.from_service_account_info(parsed)
    except:
        logging.exception("Failed to read credentials as JSON, will retry as file")
        if not os.path.exists(data):
            raise Exception("Credentials data is neither a valid service account Credential JSON nor a file : %s" % data)
        credentials = service_account.Credentials.from_service_account_file(data)
    _log_get_credentials(credentials)
    return credentials
    
def get_credentials_from_json(json_str):
    credentials = service_account.Credentials.from_service_account_info(json.loads(json_str))
    _log_get_credentials(credentials)
    return credentials

def get_credentials_from_file(json_path):
    if not os.path.exists(json_path):
        raise Exception("No credentials file at path %s" % json_path)
    credentials = service_account.Credentials.from_service_account_file(json_path)
    _log_get_credentials(credentials)
    return credentials

def ensure_no_proxy():
    no_proxy = os.environ.get('NO_PROXY', '')
    expected = ["localhost", "127.0.0.1", "metadata.google.internal", "169.254.169.254"]
    actual = [x for x in no_proxy.split(",") if len(x) > 0]
    needed = [h for h in expected if h not in actual]
    if len(needed) > 0:
        logging.info("Adding hosts to NO_PROXY: %s" % needed)
        os.environ["NO_PROXY"] = ','.join(actual + needed)
        
def _get_dss_proxy_settings():
    proxy_settings = dataiku.api_client().get_general_settings().get_raw()["proxySettings"]
    proxy_host = proxy_settings.get("host")
    proxy_port = proxy_settings.get("port", 0)
    proxy_username = proxy_settings.get("username")
    proxy_password = proxy_settings.get("password")

    if proxy_host is not None and len(proxy_host) > 0 and proxy_port > 0:
        if proxy_username is not None and proxy_password is not None:
            proxy_url = "http://%s:%s@%s:%s" % (proxy_username, proxy_password, proxy_host, proxy_port)
        else:
            proxy_url = "http://%s:%s" % (proxy_host, proxy_port)
    else:
        proxy_url = None
        
    expected = ["localhost", "127.0.0.1", "metadata.google.internal", "169.254.169.254"]
    actual = [x for x in os.environ.get('NO_PROXY', '').split(",") if len(x) > 0]
    needed = [h for h in expected if h not in actual]
    no_proxy = ','.join(actual + needed)
    
    return proxy_host, proxy_port, proxy_username, proxy_password, proxy_url, no_proxy

def get_httplib2_proxyinfo():
    proxy_host, proxy_port, proxy_username, proxy_password, proxy_url, no_proxy = _get_dss_proxy_settings()
    if proxy_host is not None and len(proxy_host) > 0 and proxy_port > 0:
        proxy_info = httplib2.ProxyInfo(httplib2.socks.PROXY_TYPE_HTTP, proxy_host, proxy_port, proxy_user=proxy_username, proxy_pass=proxy_password)
        proxy_info.bypass_hosts = no_proxy.split(',')
        return proxy_info
    else:
        return None

@contextmanager
def get_dss_proxy(env=None):
    proxy_host, proxy_port, proxy_username, proxy_password, proxy_url, no_proxy = _get_dss_proxy_settings()
    environ = env or os.environ
    previous_proxy_vars = {k: environ.get(k) for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY", "no_proxy"]}
    if proxy_url is not None:
        if len(environ.get("HTTP_PROXY", '')) > 0:
            logging.info("HTTP_PROXY already configured, leaving the environment one")
        else:
            environ["HTTP_PROXY"] = proxy_url
            environ["HTTPS_PROXY"] = proxy_url
            environ["http_proxy"] = proxy_url
            environ["https_proxy"] = proxy_url
        environ["NO_PROXY"] = no_proxy
        environ["no_proxy"] = no_proxy
    
    try:
        yield
    finally:
        for k, v in previous_proxy_vars.items():
            if environ[k] != v:
                if v is None:
                    del environ[k]
                else:
                    environ[k] = v
