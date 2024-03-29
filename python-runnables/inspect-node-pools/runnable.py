from dataiku.runnables import Runnable
import dataiku
import json, logging
from dku_google.clusters import Clusters
from dku_utils.cluster import get_cluster_from_dss_cluster

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
        
        node_pool_id = self.config.get('nodePoolId', None)
        if node_pool_id is None or len(node_pool_id) == 0:
            node_pools = cluster.get_node_pools() # CRASHES HERE
            node_pool_ids = [node_pool.name for node_pool in node_pools]
        else:
            node_pool_ids = [node_pool_id]

        node_pools = []
        for node_pool_id in node_pool_ids:
            node_pool = cluster.get_node_pool(node_pool_id)
            
            node_pool_info = node_pool.get_info()
            node_pool_info["instanceGroups"] = node_pool.get_instance_groups_info()
            
            node_pools.append('<h5>%s</h5><pre class="debug">%s</pre>' % (node_pool_id, json.dumps(node_pool_info, indent=2)))
        
        return '<div>%s</div>' % ''.join(node_pools)