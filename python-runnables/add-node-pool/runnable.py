import dataiku
import json, logging, os
from dku_google.clusters import Clusters
from dku_utils.cluster import get_cluster_from_dss_cluster
from dku_kube.nvidia_utils import create_installer_daemonset_if_needed
from dataiku.runnables import Runnable



class MyRunnable(Runnable):
    def __init__(self, project_key, config, plugin_config):
        self.project_key = project_key
        self.config = config
        self.plugin_config = plugin_config

    def get_progress_target(self):
        return None

    def run(self, progress_callback):
        cluster_data, cluster, dss_cluster_settings, dss_cluster_config = get_cluster_from_dss_cluster(self.config['clusterId'])
        
        if cluster_data.get("cluster", {}).get("autopilot", {}).get("enabled", False):
            raise Exception("Nodepools aren't accessible on autopilot clusters")

        kube_config_path = dss_cluster_settings.get_raw()['containerSettings']['executionConfigsGenericOverrides']['kubeConfigPath']

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
        node_pool_builder.with_spot_vms(node_pool_config.get('useSpotVms', False))
        node_pool_builder.with_service_account(node_pool_config.get('serviceAccountType', None),
                                               node_pool_config.get('serviceAccount', None))
        node_pool_builder.with_nodepool_labels(node_pool_config.get('nodepoolLabels', {}))
        node_pool_builder.with_nodepool_taints(node_pool_config.get('nodepoolTaints', []))
        node_pool_builder.with_nodepool_gcp_labels(node_pool_config.get('nodepoolGCPLabels', {}), cluster_data.get("cluster", {}).get("resourceLabels", {}))
        node_pool_builder.with_nodepool_tags(node_pool_config.get('networkTags', []))

        create_op = node_pool_builder.build()
        logging.info("Waiting for cluster node pool creation")
        create_op.wait_done()
        logging.info("Cluster node pool created")

        # Launch NVIDIA driver installer daemonset (will only apply on tainted gpu nodes) if it's required.
        if node_pool_config.get('withGpu', False): # GPUs are not supported on autopilot (says the GKE doc)
            create_installer_daemonset_if_needed(kube_config_path=kube_config_path)


        return '<pre class="debug">%s</pre>' % json.dumps(node_pool.get_info(), indent=2)
