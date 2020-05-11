import dataiku
import json, logging, os
from dku_google.clusters import Clusters
from dku_utils.cluster import get_cluster_from_dss_cluster
from dku_kube.nvidia_utils import create_installer_daemonset
from dataiku.runnables import Runnable



class MyRunnable(Runnable):
    def __init__(self, project_key, config, plugin_config):
        self.project_key = project_key
        self.config = config
        self.plugin_config = plugin_config
        
    def get_progress_target(self):
        return None

    def run(self, progress_callback):
        cluster_data, clusters, dss_cluster_settings, dss_cluster_config = get_cluster_from_dss_cluster(self.config['clusterId'])
        
        kube_config_path = dss_cluster_settings.get_raw()['containerSettings']['executionConfigsGenericOverrides']['kubeConfigPath']
        
        # retrieve the actual name in the cluster's data
        if cluster_data is None:
            raise Exception("No cluster data (not started?)")
        cluster_def = cluster_data.get("cluster", None)
        if cluster_def is None:
            raise Exception("No cluster definition (starting failed?)")
        cluster_name = cluster_def["name"]
        
        # get the object for the cluster, GKE side
        cluster = clusters.get_cluster(cluster_name)
        
        node_pool_id = self.config.get('nodePoolId', None)
        node_pools = cluster.get_node_pools()
        if node_pool_id is None or len(node_pool_id) == 0:
            node_pool_ids = [node_pool.name for node_pool in node_pools]
            cnt = 0
            while ('node-pool-%s' % cnt) in node_pool_ids:
                cnt += 1
            node_pool_id = 'node-pool-%s' % cnt
        
        node_pool = cluster.get_node_pool(node_pool_id)
        
        node_pool_config = self.config.get("nodePoolConfig", {})
        node_pool_builder = node_pool.get_node_pool_builder()
        node_pool_builder.with_node_count(node_pool_config.get('numNodes', 3))
        node_pool_builder.use_gcr_io(node_pool_config.get('useGcrIo', False))
        node_pool_builder.with_oauth_scopes(node_pool_config.get('oauthScopes', None))
        node_pool_builder.with_machine_type(node_pool_config.get('machineType', None))
        node_pool_builder.with_disk_type(node_pool_config.get('diskType', None))
        node_pool_builder.with_disk_size_gb(node_pool_config.get('diskSizeGb', None))
        node_pool_builder.with_gpu(node_pool_config.get('withGpu', False),
                                   node_pool_config.get('gpuType', None),
                                   node_pool_config.get('gpuCount', 1))
        node_pool_builder.with_service_account(node_pool_config.get('serviceAccountType', None),
                                               node_pool_config.get('serviceAccount', None))
        node_pool_builder.with_nodepool_labels(node_pool_config.get('nodepoolLabels', {}))
        
        create_op = node_pool_builder.build()
        logging.info("Waiting for cluster node pool creation")
        create_op.wait_done()
        logging.info("Cluster node pool created")

        # Launch NVIDIA driver installer daemonset (will only apply on tainted gpu nodes)
        create_installer_daemonset(kube_config_path=kube_config_path)


        return '<pre class="debug">%s</pre>' % json.dumps(node_pool.get_info(), indent=2)
