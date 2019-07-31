from google.oauth2 import service_account
import os, sys, json
import logging

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
