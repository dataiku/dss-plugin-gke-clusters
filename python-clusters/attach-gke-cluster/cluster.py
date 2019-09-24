import os, sys, json, subprocess, time, logging, yaml

from dataiku.cluster import Cluster

from dku_google.auth import get_credentials_from_json_or_file
from dku_google.clusters import Clusters
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
        # retrieve the cluster info from GKE
        # this will fail if the cluster doesn't exist, but the API message is enough
        clusters = get_cluster_from_connection_info(self.config['connectionInfo'], self.plugin_config['connectionInfo'])
                
        cluster = clusters.get_cluster(self.config.get('clusterId', self.cluster_name))
        cluster_info = cluster.get_info()

        # build the config file for kubectl
        # we don't add the context to the main config file, to not end up with an oversized config,
        # and because 2 different clusters could be concurrently editing the config file
        kube_config_path = os.path.join(os.getcwd(), 'kube_config')
        kube_config = cluster.get_kube_config(self.cluster_id)
        with open(kube_config_path, 'w') as f:
            yaml.safe_dump(kube_config, f, default_flow_style=False)
                
        # add the admin role so that we can do the managed kubernetes stuff for spark
        create_admin_binding(self.config.get("userName", None), kube_config_path)
        
        # collect and prepare the overrides so that DSS can know where and how to use the cluster
        overrides = make_overrides(self.config, kube_config, kube_config_path)
        return [overrides, {'kube_config_path':kube_config_path, 'cluster':cluster_info}]

    def stop(self, data):
        pass
