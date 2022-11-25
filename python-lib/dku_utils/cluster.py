from dku_utils.access import _default_if_blank, _default_if_property_blank
import dataiku
import yaml
from dku_google.auth import get_credentials_from_json_or_file
from dku_google.clusters import Clusters
from dataiku.core.intercom import backend_json_call
from dku_utils.access import _has_not_blank_property
import json, logging, re

def make_overrides(kube_config_path):
    with open(kube_config_path, "r") as f:
        kube_config = yaml.safe_load(f)
    
    # alter the spark configurations to put the cluster master and image repo in the properties
    container_settings = {
                            'executionConfigsGenericOverrides': {
                                'kubeCtlContext': kube_config["current-context"], # has to exist, it's a config file we just built
                                'kubeConfigPath': kube_config_path, # the config is not merged into the main config file, so we need to pass the config file pth
                            }
                        }
    spark_settings = {
                        "sparkEnabled": True
                    }
    return {'spark':spark_settings, 'container':container_settings}

def get_cluster_from_connection_info(config_connection_info, plugin_config_connection_info):
    credentials = None
    if _has_not_blank_property(plugin_config_connection_info, 'credentials'):
        credentials = get_credentials_from_json_or_file(plugin_config_connection_info['credentials'])
    return Clusters(config_connection_info.get("projectId", None), config_connection_info.get("zone", None), config_connection_info.get("region", None), credentials)

def get_cluster_from_dss_cluster(dss_cluster_id):
    # get the public API client
    client = dataiku.api_client()

    # get the cluster object in DSS
    found = False
    for c in client.list_clusters():
        if c['name'] == dss_cluster_id:
            found = True
    if not found:
        raise Exception("DSS cluster %s doesn't exist" % dss_cluster_id)
    dss_cluster = client.get_cluster(dss_cluster_id)

    # get the settings in it
    dss_cluster_settings = dss_cluster.get_settings()
    dss_cluster_config = dss_cluster_settings.get_raw()['params']['config']
    # resolve since we get the config with the raw preset setup
    dss_cluster_config = backend_json_call('plugins/get-resolved-settings', data={'elementConfig':json.dumps(dss_cluster_config), 'elementType':dss_cluster_settings.get_raw()['type']})
    logging.info("Resolved cluster config : %s" % json.dumps(dss_cluster_config))
    # build the helper class from the cluster settings (the macro doesn't have the params)
    clusters = get_cluster_from_connection_info(dss_cluster_config['config']['connectionInfo'], dss_cluster_config['pluginConfig']['connectionInfo'])

    cluster_data = dss_cluster_settings.get_plugin_data()
    
    if cluster_data is None:
        raise Exception("No cluster data (not started?)")
    cluster_def = cluster_data.get("cluster", None)
    if cluster_def is None:
        raise Exception("No cluster definition (starting failed?)")
    cluster_name = cluster_def["name"]

    self_link = cluster_def.get('selfLink', None)
    if self_link is None:
        raise Exception("No selflink found, cluster is probably not running")
    if re.match('https://[^/]+/v1/projects/[^/]+/zones/[^/]+/clusters/[^/]+', self_link):
        definition_level = 'zonal'
    else:
        definition_level = 'regional'
        
    cluster = clusters.get_cluster(cluster_name, definition_level)

    return cluster_data, cluster, dss_cluster_settings, dss_cluster_config
    
