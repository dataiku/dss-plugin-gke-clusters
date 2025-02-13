import logging
import os
import requests
from dku_utils.access import _is_none_or_blank

DEFAULT_HEADERS={"User-Agent": "DSS GKE Plugin"}

def download_to_disk(url, download_location=None):
    if _is_none_or_blank(url):
        logging.error("URL '%s' is none or blank." % url)
        return

    if _is_none_or_blank(download_location):
        local_path = url.split('/')[-1]
    else:
        local_path = download_location

    r = requests.get(url, headers=DEFAULT_HEADERS)
    if r.ok:
        logging.debug("Successfully retrieved content from URL '%s'." % url)
        logging.debug("Writing contents into path '%s'." % local_path)
        with open(local_path, "w") as f:
            f.write(r.text)

        return os.path.abspath(local_path)
    else:
        logging.error("Retrieving the file from URL '%s' failed with status: %s %s" % (url, r.status_code, r.reason))
        logging.error("Content of failed request: %s" % r.content)
        logging.error("Unable to retrieve the contents from URL '%s'." % url)

def get_static_resource_path(static_resource_filename):
    return os.path.join(os.environ["DKU_CUSTOM_RESOURCE_FOLDER"], static_resource_filename)