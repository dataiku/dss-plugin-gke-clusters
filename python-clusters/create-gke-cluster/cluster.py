import os, sys, json, subprocess, time, logging, yaml
from dataiku.cluster import Cluster



from dku_google.auth import get_credentials_from_json_or_file
from dku_google.clusters import Clusters
from dku_google.gcloud import create_kube_config_file
from dku_kube.kubeconfig import merge_or_write_config
from dku_kube.role import create_admin_binding
from dku_kube.nvidia_utils import create_installer_daemonset_if_needed
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

        # build the create cluster request
        clusters = get_cluster_from_connection_info(self.config['connectionInfo'], self.plugin_config['connectionInfo'])
        
        is_autopilot = self.config.get("isAutopilot", False)
        is_regional = is_autopilot or self.config.get('isRegional', False)
        
        cluster_builder = clusters.new_cluster_builder()
        
        cluster_builder.with_name(self.cluster_name)
        if is_autopilot:
            cluster_builder.with_regional(True, []) # autopilot => regional
            cluster_builder.with_autopilot(True)
            cluster_builder.with_release_channel(self.config.get("releaseChannel", "STABLE"))
        else:
            cluster_builder.with_version(self.config.get("clusterVersion", "latest"))
            cluster_builder.with_release_channel_enrollment(self.config.get("releaseChannelEnrollment", True))
            cluster_builder.with_release_channel(self.config.get("standardReleaseChannel", "DEFAULT"))
            cluster_builder.with_initial_node_count(self.config.get("numNodes", 3))


        cluster_builder.with_network(self.config.get("inheritFromDSSHost", True),
                                     self.config.get("network", "").strip(),
                                     self.config.get("subNetwork", "").strip())
        vpc_native = is_autopilot or self.config.get("isVpcNative", None)
        cluster_builder.with_vpc_native_settings(vpc_native,
                                                 self.config.get("podIpRange", ""),
                                                 self.config.get("svcIpRange", ""))
        cluster_builder.with_labels(self.config.get("clusterLabels", {}))
        cluster_builder.with_partner_google_urn(MyCluster.resolve_partner_google_urn())
        has_gpu = False

        if not is_autopilot:
            cluster_builder.with_http_load_balancing(self.config.get("httpLoadBalancing", False))
            if is_regional:
                cluster_builder.with_regional(True, self.config.get("locations", []))
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
                node_pool_builder.with_spot_vms(node_pool.get('useSpotVms', False))
                node_pool_builder.with_nodepool_labels(node_pool.get('nodepoolLabels', {}))
                node_pool_builder.with_nodepool_taints(node_pool.get('nodepoolTaints', []))
                node_pool_builder.with_nodepool_gcp_labels(node_pool.get('nodepoolGCPLabels', {}), cluster_builder.labels)
                node_pool_builder.with_nodepool_tags(node_pool.get('networkTags', []))
                node_pool_builder.build()

                has_gpu |= node_pool.get('withGpu', False)
        cluster_builder.with_settings_valve(self.config.get("creationSettingsValve", None))
        
        start_op = cluster_builder.build()
        
        # can take a few mins...
        logging.info("Waiting for cluster start")
        start_op.wait_done()
        logging.info("Cluster started")
        
        # cluster is ready, fetch its info from GKE
        cluster = clusters.get_cluster(self.cluster_name, 'regional' if is_regional else 'zonal')
        cluster_info = cluster.get_info()

        # delegate the creation of the kube config file to gcloud to use the client go auth plugin
        kube_config_path = os.path.join(os.getcwd(), 'kube_config')
        region_or_zone = clusters.region if is_regional else clusters.zone
        create_kube_config_file(clusters.project_id, self.cluster_id, is_regional, region_or_zone, kube_config_path)
        
        # add the admin role so that we can do the managed kubernetes stuff for spark
        create_admin_binding(self.config.get("userName", None), kube_config_path)
        
        # Launch NVIDIA driver installer daemonset (will only apply on tainted gpu nodes)
        if not is_autopilot and has_gpu: # GPUs are not supported on autopilot (says the GKE doc)
            create_installer_daemonset_if_needed(kube_config_path=kube_config_path)
        
        # collect and prepare the overrides so that DSS can know where and how to use the cluster
        overrides = make_overrides(kube_config_path)
        return [overrides, {'kube_config_path':kube_config_path, 'cluster':cluster_info}]

    def stop(self, data):
        clusters = get_cluster_from_connection_info(self.config['connectionInfo'], self.plugin_config['connectionInfo'])  
        is_autopilot = self.config.get("isAutopilot", False)
        is_regional = is_autopilot or self.config.get('isRegional', False)
        cluster = clusters.get_cluster(self.cluster_name, 'regional' if is_regional else 'zonal')
        stop_op = cluster.stop()    
        logging.info("Waiting for cluster stop")
        stop_op.wait_done()
        logging.info("Cluster stopped")

    @staticmethod
    def resolve_partner_google_urn():
        full_path = os.path.join(os.environ.get("DIP_HOME"), "config", "license.json")
        try:
            with open(full_path) as license_file:
                _license = json.load(license_file)
                return _license["content"]["properties"]["partner.google.urn"]
        except Exception:
            return "isol_psn_0014m00001h39q5qai_dataiku"
