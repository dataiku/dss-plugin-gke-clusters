import os

try:
    from urllib.parse import quote
except ImportError:
    from urllib import quote


def configure_proxy_environment():
    """Configure this plugin process before creating HTTP clients or child environments.

    Existing values win per protocol, with lowercase taking precedence over
    uppercase. DSS supplies only protocols missing from the environment.
    """
    # Configure bypasses before querying DSS, which may itself use a local URL.
    bypass_hosts = []
    for key in ("no_proxy", "NO_PROXY"):
        for host in os.environ.get(key, "").split(","):
            host = host.strip()
            if host and host not in bypass_hosts:
                bypass_hosts.append(host)
    for host in ("localhost", "127.0.0.1", "::1", "metadata",
                 "metadata.google.internal", "169.254.169.254"):
        if host not in bypass_hosts:
            bypass_hosts.append(host)
    # httplib2 recognizes the wildcard only when it is the entire value.
    no_proxy = "*" if "*" in bypass_hosts else ",".join(bypass_hosts)
    os.environ["NO_PROXY"] = no_proxy
    os.environ["no_proxy"] = no_proxy

    proxies = {}
    for protocol in ("http", "https"):
        key = protocol + "_proxy"
        proxies[protocol] = os.environ.get(key) or os.environ.get(key.upper())

    if not all(proxies.values()):
        import dataiku
        settings = dataiku.get_dss_settings().get("globalProxy") or {}
        host = settings.get("host")
        port = settings.get("port") or 0
        if host and port > 0:
            # Brackets are required around literal IPv6 proxy addresses.
            if ":" in host and not host.startswith("["):
                host = "[{}]".format(host)
            username = settings.get("username")
            password = settings.get("password") or ""
            auth = ""
            if username:
                auth = "{}:{}@".format(quote(username.encode("utf-8"), safe=""),
                                      quote(password.encode("utf-8"), safe=""))
            proxy_url = "http://{}{}:{}".format(auth, host, port)
            for protocol in proxies:
                if not proxies[protocol]:
                    proxies[protocol] = proxy_url

    for protocol, proxy_url in proxies.items():
        if proxy_url:
            key = protocol + "_proxy"
            os.environ[key] = proxy_url
            os.environ[key.upper()] = proxy_url
