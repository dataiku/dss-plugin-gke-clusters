import os, sys, json, subprocess, time, logging, yaml

from dataiku.cluster import Cluster

from dku_google.auth import get_credentials_from_json_or_file
from dku_google.clusters import Clusters
from dku_google.gcloud import create_kube_config_file
from dku_kube.kubeconfig import merge_or_write_config
from dku_kube.role import create_admin_binding
from dku_utils.cluster import make_overrides, get_cluster_from_connection_info
from dku_utils.access import _has_not_blank_property

class MyCluster(Cluster):
    def __init__(self, cluster_id, cluster_name, config, plugin_config, global_settings):
        self.cluster_id = cluster_id
        self.cluster_name = cluster_name
        self.config = config
        self.plugin_config = plugin_config
        self.global_settings = global_settings
        
    def start(self):
        logging.getLogger().setLevel(self.config.get('logLevel', 'INFO'))

        # retrieve the cluster info from GKE
        # this will fail if the cluster doesn't exist, but the API message is enough
        clusters = get_cluster_from_connection_info(self.config['connectionInfo'], self.plugin_config['connectionInfo'])
                
        is_regional = self.config.get('isRegional', False)
        cluster = clusters.get_cluster(self.config.get('clusterId', self.cluster_name), 'regional' if is_regional else 'zonal')
        cluster_info = cluster.get_info()

        # delegate the creation of the kube config file to gcloud to use the client go auth plugin
        kube_config_path = os.path.join(os.getcwd(), 'kube_config')
        region_or_zone = clusters.region if is_regional else clusters.zone
        is_dns_endpoint = self.config.get('isDnsEndpoint', False)
        create_kube_config_file(clusters.project_id, cluster.name, is_regional, region_or_zone, kube_config_path, is_dns_endpoint)
                
        # add the admin role so that we can do the managed kubernetes stuff for spark
        create_admin_binding(self.config.get("userName", None), kube_config_path)
        
        # collect and prepare the overrides so that DSS can know where and how to use the cluster
        overrides = make_overrides(kube_config_path)
        return [overrides, {'kube_config_path':kube_config_path, 'cluster':cluster_info}]

    def stop(self, data):
        pass
