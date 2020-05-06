import os, sys, json, subprocess, time, logging, yaml
from dataiku.cluster import Cluster



from dku_google.auth import get_credentials_from_json_or_file
from dku_google.clusters import Clusters
from dku_kube.kubeconfig import merge_or_write_config
from dku_kube.role import create_admin_binding
from dku_kube.nvidia_utils import create_installer_daemonset
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
        # build the create cluster request
        clusters = get_cluster_from_connection_info(self.config['connectionInfo'], self.plugin_config['connectionInfo'])
        
        cluster_builder = clusters.new_cluster_builder()
        
        cluster_builder.with_name(self.cluster_name)
        cluster_builder.with_version(self.config.get("clusterVersion", "latest"))
        cluster_builder.with_initial_node_count(self.config.get("numNodes", 3))
        cluster_builder.with_network(self.config.get("inheritFromDSSHost", True),
                                     self.config.get("network", "").strip(),
                                     self.config.get("subNetwork", "").strip())
        cluster_builder.with_vpc_native_settings(self.config.get("isVpcNative", None),
                                                 self.config.get("podIpRange", ""),
                                                 self.config.get("svcIpRange", ""))
        cluster_builder.with_labels(self.config.get("clusterLabels", {}))
        cluster_builder.with_legacy_auth(self.config.get("legacyAuth", False))
        cluster_builder.with_http_load_balancing(self.config.get("httpLoadBalancing", False))
        for node_pool in self.config.get('nodePools', []):
            node_pool_builder = cluster_builder.get_node_pool_builder()
            node_pool_builder.with_node_count(node_pool.get('numNodes', 3))
            node_pool_builder.use_gcr_io(node_pool.get('useGcrIo', False))
            node_pool_builder.with_oauth_scopes(node_pool.get('oauthScopes', None))
            node_pool_builder.with_machine_type(node_pool.get('machineType', None))
            node_pool_builder.with_disk_type(node_pool.get('diskType', None))
            node_pool_builder.with_disk_size_gb(node_pool.get('diskSizeGb', None))
            node_pool_builder.with_service_account(node_pool.get('serviceAccountType', None),
                                                   node_pool.get('serviceAccount', None))
            node_pool_builder.with_auto_scaling(node_pool.get('numNodesAutoscaling', False), node_pool.get('minNumNodes', 2), node_pool.get('maxNumNodes', 5))
            node_pool_builder.with_gpu(node_pool.get('withGpu', False), node_pool.get('gpuType', None), node_pool.get('gpuCount', 1))
            node_pool_builder.with_nodepool_labels(node_pool.get('nodepoolLabels', {}))
            node_pool_builder.build()
        cluster_builder.with_settings_valve(self.config.get("creationSettingsValve", None))
        
        start_op = cluster_builder.build()
        
        # can take a few mins...
        logging.info("Waiting for cluster start")
        start_op.wait_done()
        logging.info("Cluster started")
        
        # cluster is ready, fetch its info from GKE
        cluster = clusters.get_cluster(self.cluster_name)
        cluster_info = cluster.get_info()
        
        # build the config file for kubectl
        # we don't add the context to the main config file, to not end up with an oversized config,
        # and because 2 different clusters could be concurrently editing the config file
        kube_config_path = os.path.join(os.getcwd(), 'kube_config')
        kube_config = cluster.get_kube_config()
        with open(kube_config_path, 'w') as f:
            yaml.safe_dump(kube_config, f, default_flow_style=False)
        
        # add the admin role so that we can do the managed kubernetes stuff for spark
        create_admin_binding(self.config.get("userName", None), kube_config_path)
        
        # Launch NVIDIA driver installer daemonset (will only apply on tainted gpu nodes)
        create_installer_daemonset(kube_config_path=kube_config_path) 
        
        # collect and prepare the overrides so that DSS can know where and how to use the cluster
        overrides = make_overrides(self.config, kube_config, kube_config_path)
        return [overrides, {'kube_config_path':kube_config_path, 'cluster':cluster_info}]

    def stop(self, data):
        clusters = get_cluster_from_connection_info(self.config['connectionInfo'], self.plugin_config['connectionInfo'])  
        cluster = clusters.get_cluster(self.cluster_name)
        stop_op = cluster.stop()    
        logging.info("Waiting for cluster stop")
        stop_op.wait_done()
        logging.info("Cluster stopped")

