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
        cluster_data, clusters, dss_cluster_settings, dss_cluster_config = get_cluster_from_dss_cluster(self.config['clusterId'])

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
            if len(node_pool_ids) != 1:
                raise Exception("Cluster has %s node pools, cannot resize. Specify a node pool explicitely among %s" % (len(node_pool_ids), json.dumps(node_pool_ids)))
            node_pool_id = node_pool_ids[0]
        
        node_pool = cluster.get_node_pool(node_pool_id)
        
        desired_count = self.config['numNodes']
        logging.info("Resize to %s" % desired_count)
        if desired_count == 0:
            delete_op = node_pool.delete()
            logging.info("Waiting for cluster node pool delete")
            delete_op.wait_done()
            logging.info("Cluster node pool deleted")
            node_pool_ids = [node_pool.name for node_pool in cluster.get_node_pools()]
            return '<pre class="debug">%s</pre>' % json.dumps(node_pool_ids, indent=2)
        else:
            resize_op = node_pool.resize(self.config['numNodes'])
            logging.info("Waiting for cluster resize")
            resize_op.wait_done()
            logging.info("Cluster resized")
            return '<pre class="debug">%s</pre>' % json.dumps(node_pool.get_info(), indent=2)