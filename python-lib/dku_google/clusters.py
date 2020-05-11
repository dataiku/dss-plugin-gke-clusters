from googleapiclient import discovery
from six import text_type
from googleapiclient.errors import HttpError
from dku_google.gcloud import get_sdk_root, get_access_token_and_expiry, get_instance_info
from dku_google.gcloud import get_instance_network, get_instance_service_account
from dku_utils.access import _has_not_blank_property, _is_none_or_blank, _default_if_blank, _merge_objects

import os, sys, json, re
import logging

from .operations import Operation

class NodePoolBuilder(object):
    def __init__(self, cluster_builder):
        self.cluster_builder = cluster_builder
        self.node_count = None
        self.machine_type = None
        self.disk_type = None
        self.disk_size_gb = None
        self.oauth_scopes = []
        self.name = None
        self.settings_valve = None
        self.min_node_count = None
        self.max_node_count = None
        self.enable_autoscaling = False
        self.enable_gpu = False
        self.gpu_type = None
        self.gpu_count = None
        self.service_account = None
        self.nodepool_labels = {}
 
    def with_name(self, name):
        self.name = name
        return self
    
    def with_node_count(self, node_count):
        self.node_count = node_count
        return self
    
    def with_auto_scaling(self, enable, min_count, max_count):
        self.min_node_count = min_count
        self.max_node_count = max_count
        self.enable_autoscaling = enable
        return self
    
    def add_oauth_scope(self, oauth_scope):
        if oauth_scope not in self.oauth_scopes:
            self.oauth_scopes.append(oauth_scope)
    
    def use_gcr_io(self, use_gcr_io):
        if use_gcr_io == True:
            self.add_oauth_scope("https://www.googleapis.com/auth/devstorage.read_only")
        return self
    
    def with_oauth_scopes(self, oauth_scopes):
        if isinstance(oauth_scopes, text_type):
            return self.with_oauth_scopes(oauth_scopes.split(','))
        if oauth_scopes is not None:
            for oauth_scope in oauth_scopes:
                if _is_none_or_blank(oauth_scope):
                    continue
                self.add_oauth_scope(oauth_scope.strip())
        return self
    
    def with_machine_type(self, machine_type):
        self.machine_type = machine_type
        return self
    
    def with_disk_type(self, disk_type):
        self.disk_type = disk_type
        return self
    
    def with_disk_size_gb(self, disk_size_gb):
        self.disk_size_gb = disk_size_gb
        return self
    
    def with_service_account(self, service_account_type, custom_service_account_name):
        """
        Change default service account on cluster nodes.
        Requires the iam.serviceAccountUser IAM permission.
        """

        if service_account_type == "fromDSSHost":
            logging.info("Custer nodes will inherit the DSS host Service Account")
            self.service_account = get_instance_service_account()
        if service_account_type == "custom":
            if _is_none_or_blank(custom_service_account_name):
                logging.info("Cluster nodes will have the default Compute Engine Service Account")
                self.service_account = ""
            else:
                logging.info("Cluster nodes will have the custom Service Account: {}".format(custom_service_account_name))
                self.service_account = custom_service_account_name
        return self
    
    def with_settings_valve(self, settings_valve):
        self.settings_valve = _default_if_blank(settings_valve, None)
        return self

    def with_gpu(self, enable_gpu, gpu_type, gpu_count):
        self.enable_gpu = enable_gpu
        self.gpu_type = gpu_type
        self.gpu_count = gpu_count
        return self

    def with_nodepool_labels(self, nodepool_labels=[]):
        if nodepool_labels:
            nodepool_labels_dict = {l["from"]: l["to"] for l in nodepool_labels}
            logging.info("Adding labels {} to node pool {}".format(nodepool_labels_dict, self.name))
            self.nodepool_labels.update(nodepool_labels_dict)
        return self

    def build(self):
        node_pool = {'config':{}}
        node_pool['name'] = self.name if self.name is not None else 'node-pool'
        node_pool['initialNodeCount'] = self.node_count if self.node_count is not None else 3
        if self.machine_type is not None:
            node_pool['config']['machineType'] = self.machine_type
        if self.disk_type is not None:
            node_pool['config']['diskType'] = self.disk_type
        # Add optional GPU accelerator:
        if self.enable_gpu:
            logging.info("GPU option enabled.")
            node_pool['config']['accelerators'] = [{'acceleratorCount': self.gpu_count,
                                                    'acceleratorType': self.gpu_type}]
        if self.disk_size_gb is not None and self.disk_size_gb > 0:
            node_pool['config']['diskSizeGb'] = self.disk_size_gb
        node_pool['config']['oauthScopes'] = self.oauth_scopes
        
        if not _is_none_or_blank(self.service_account):
            node_pool['config']['serviceAccount'] = self.service_account
            
        node_pool["management"] = {
            "autoUpgrade": True,
            "autoRepair": True
        }
        if self.enable_autoscaling:
            node_pool['autoscaling'] = {
                                            "enabled":True,
                                            "minNodeCount":self.min_node_count if self.min_node_count is not None else node_pool['initialNodeCount'],
                                            "maxNodeCount":self.max_node_count if self.max_node_count is not None else node_pool['initialNodeCount']
                                        }
        node_pool["config"]["labels"] = self.nodepool_labels
            
        if not _is_none_or_blank(self.settings_valve):
            valve = json.loads(self.settings_valve)
            node_pool = _merge_objects(node_pool, valve)

        if isinstance(self.cluster_builder, ClusterBuilder):
            self.cluster_builder.with_node_pool(node_pool)
        elif isinstance(self.cluster_builder, NodePool):
            return self.cluster_builder.create(node_pool)
        else:
            raise Exception("Unreachable")


class ClusterBuilder(object):
    def __init__(self, clusters):
        self.clusters = clusters
        self.name = None
        self.version = None
        self.node_count = None
        self.network = None
        self.subnetwork = None
        self.labels = {}
        self.is_vpc_native = None
        self.pod_ip_range = None
        self.svc_ip_range = None
        self.legacy_auth = False
        self.http_load_balancing = None
        self.node_pools = []
        self.settings_valve = None
       
    def with_name(self, name):
        self.name = name
        return self
    
    def with_version(self, version):
        self.version = version
        return self
    
    def with_network(self, is_same_network_as_dss, network, subnetwork):
        self.is_same_network_as_dss = is_same_network_as_dss
        if self.is_same_network_as_dss:
            logging.info("Cluster network/subnetwork is the SAME AS DSS HOST")
            self.network, self.subnetwork = get_instance_network()
        else:
            logging.info("Cluster network/subnetwork is set EXPLICITLY")
            self.network = _default_if_blank(network, None)
            self.subnetwork = _default_if_blank(subnetwork, None)
        logging.info("Cluster network is {}".format(self.network))
        logging.info("Cluster subnetwork is {}".format(self.subnetwork))
        return self
    
    def get_node_pool_builder(self):
        return NodePoolBuilder(self).with_name('node-pool-%s' % len(self.node_pools))
    
    def with_node_pool(self, node_pool):
        self.node_pools.append(node_pool)
        return self
    
    def with_initial_node_count(self, node_count):
        self.node_count = node_count
        return self
    
    def with_labels(self, labels={}):
        self.labels.update(labels)
        if self.labels:
            logging.info("Adding labels {}".format(str(self.labels)))
        return self

    def with_vpc_native_settings(self, is_vpc_native, pod_ip_range, svc_ip_range):
        if is_vpc_native:
            self.is_vpc_native = is_vpc_native
            self.pod_ip_range = pod_ip_range
            self.svc_ip_range = svc_ip_range
        return self
    
    def with_legacy_auth(self, legacy_auth):
        self.legacy_auth = legacy_auth
        return self
    
    def with_http_load_balancing(self, http_load_balancing):
        self.http_load_balancing = http_load_balancing
        return self

    def with_settings_valve(self, settings_valve):
        self.settings_valve = _default_if_blank(settings_valve, None)
        return self

    def _auto_name(self):
        return 'dku-cluster-' + ''.join([random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for i in range(0, 8)])
    
    def build(self):
        cluster_name = self.name
        cluster_version = self.version
        cluster_node_count = self.node_count
        cluster_network = self.network
        cluster_subnetwork = self.subnetwork
        cluster_labels = self.labels
        cluster_pod_ip_range = self.pod_ip_range
        cluster_svc_ip_range = self.svc_ip_range
        
        if _is_none_or_blank(cluster_name):
            cluster_name = self._auto_name()
        if cluster_node_count is None:
            cluster_node_count = 3
            
        create_cluster_request_body = {
            "cluster" : {
                "name": cluster_name,
                "initialClusterVersion": cluster_version,
                "description": "Created from plugin",
                "network": cluster_network,
                "subnetwork": cluster_subnetwork,
                "resourceLabels": cluster_labels,
                "nodePools": []
            },
            "parent" : self.clusters.get_location()
        }
        if self.is_vpc_native:
            ip_allocation_policy = {
                "createSubnetwork": False,
                "useIpAliases": True,
                "servicesIpv4CidrBlock": cluster_svc_ip_range,
                "clusterIpv4CidrBlock": cluster_pod_ip_range,
            }
            create_cluster_request_body["cluster"]["ipAllocationPolicy"] = ip_allocation_policy

        if self.legacy_auth:
            create_cluster_request_body["cluster"]["legacyAbac"] = {"enabled":True}
            
        need_issue_certificate = False

        if cluster_version == "latest" or cluster_version == "-":
            need_issue_certificate = True
        else:
            version_chunks = cluster_version.split('.')
            major_version = int(version_chunks[0])
            minor_version = int(version_chunks[1])
            need_issue_certificate = major_version > 1 or (major_version == 1 and minor_version >= 12)
                
        if need_issue_certificate:
            create_cluster_request_body["cluster"]["masterAuth"] = {
                                                                        "clientCertificateConfig" : {
                                                                            "issueClientCertificate" : True
                                                                        }
                                                                    }
        
        create_cluster_request_body["cluster"]["addonsConfig"] = {}
        if self.http_load_balancing:
            create_cluster_request_body["cluster"]["addonsConfig"]["httpLoadBalancing"] = {"disabled":False}
        else:
            create_cluster_request_body["cluster"]["addonsConfig"]["httpLoadBalancing"] = {"disabled":True}

        for node_pool in self.node_pools:
            create_cluster_request_body['cluster']['nodePools'].append(node_pool)
            
        if not _is_none_or_blank(self.settings_valve):
            valve = json.loads(self.settings_valve)
            create_cluster_request_body["cluster"] = _merge_objects(create_cluster_request_body["cluster"], valve)
                
        logging.info("Requesting cluster %s" % json.dumps(create_cluster_request_body, indent=2))
                
        location_params = self.clusters.get_location_params()
        request = self.clusters.get_clusters_api().create(body=create_cluster_request_body, **location_params)
        
        try:
            response = request.execute()
            return Operation(response, self.clusters.get_operations_api(), self.clusters.get_location_params())
        except HttpError as e:
            raise Exception("Failed to create cluster : %s" % str(e))
    
class NodePool(object):
    def __init__(self, name, cluster):
        self.name = name
        self.cluster = cluster
        
    def get_info(self):
        location_params = self.cluster.get_location_params()
        request = self.cluster.get_node_pools_api().get(nodePoolId=self.name, **location_params)
        response = request.execute()
        return response
    
    def get_instance_groups_info(self):
        node_pool_info = self.get_info()
        instance_groups = []
        for instance_group_url in node_pool_info.get("instanceGroupUrls", []):
            instance_group_name = re.match("^.*/([^/]+)", instance_group_url).group(1)
            location_params = self.cluster.get_parent_location_params()
            request = self.cluster.get_instance_groups_api().get(instanceGroup=instance_group_name, project=location_params["projectId"], zone=location_params["zone"])
            instance_groups.append(request.execute())
        return instance_groups
        
    def resize(self, num_nodes):
        resize_cluster_request_body = {
            "nodeCount" : num_nodes
        }

        location_params = self.cluster.get_location_params()
        request = self.cluster.get_node_pools_api().setSize(nodePoolId=self.name, body=resize_cluster_request_body, **location_params)
        try:
            response = request.execute()
            return Operation(response, self.cluster.get_operations_api(), self.cluster.get_parent_location_params())
        except HttpError as e:
            raise Exception("Failed to resize node pool : %s" % str(e))
        
    def delete(self):
        location_params = self.cluster.get_location_params()
        request = self.cluster.get_node_pools_api().delete(nodePoolId=self.name, **location_params)
        try:
            response = request.execute()
            return Operation(response, self.cluster.get_operations_api(), self.cluster.get_parent_location_params())
        except HttpError as e:
            raise Exception("Failed to delete node pool : %s" % str(e))
        
    def get_node_pool_builder(self):
        return NodePoolBuilder(self).with_name(self.name)
    
    def create(self, node_pool_config):
        create_node_pool_request_body = {
            "nodePool" : node_pool_config,
            "parent" : self.cluster.get_location()
        }
        
        logging.info("Requesting node pool %s" % json.dumps(create_node_pool_request_body, indent=2))
                
        location_params = self.cluster.get_location_params()
        request = self.cluster.get_node_pools_api().create(body=create_node_pool_request_body, **location_params)
        
        try:
            response = request.execute()
            return Operation(response, self.cluster.get_operations_api(), self.cluster.get_parent_location_params())
        except HttpError as e:
            raise Exception("Failed to create node pool : %s" % str(e))

class Cluster(object):
    def __init__(self, name, clusters):
        self.name = name
        self.clusters = clusters
        
    def get_location(self):
        return "%s/clusters/%s" % (self.clusters.get_location(), self.name)
        
    def get_parent_location_params(self):
        return self.clusters.get_location_params()
    
    def get_location_params(self):
        params = self.clusters.get_location_params().copy()
        params["clusterId"] = self.name
        return params
    
    def get_node_pools_api(self):
        return self.clusters.get_clusters_api().nodePools()
    
    def get_operations_api(self):
        return self.clusters.get_operations_api()
        
    def get_instance_groups_api(self):
        return self.clusters.get_instance_groups_api()
        
    def get_info(self):
        location_params = self.clusters.get_location_params()
        request = self.clusters.get_clusters_api().get(clusterId=self.name, **location_params)
        response = request.execute()
        return response

    def get_kube_config(self, cluster_id=None):
        response = self.get_info()
        
        if _is_none_or_blank(cluster_id):
            cluster_id = self.name
            
        logging.info("Response=%s" % json.dumps(response, indent=2))
            
        legacy_auth = response.get("legacyAbac", {}).get("enabled", False)
        master_auth = response["masterAuth"]
        endpoint = response["endpoint"]
        
        user = {
            "name": "user-%s" % cluster_id,
            "user": {}
        }
        if legacy_auth:
            user["user"] = {
                                "client-certificate-data": master_auth["clientCertificate"],
                                "client-key-data": master_auth["clientKey"]
                            }
        else:
            user["user"] = {
                                "auth-provider": {
                                    "name": "gcp",
                                    "config": {
                                        "cmd-args": "config config-helper --format=json",
                                        "cmd-path" : os.path.join(get_sdk_root(), "bin", "gcloud"),
                                        "expiry-key": "{.credential.token_expiry}",
                                        "token-key": "{.credential.access_token}"
                                    }
                                }
                            }
        
        cluster = {
            "name": "cluster-%s" % cluster_id,
            "cluster": {
                "certificate-authority-data": master_auth["clusterCaCertificate"],
                "server": "https://%s" % endpoint
            }
        }
        context = {
            "name": "context-%s" % cluster_id,
            "context": {
                "cluster": cluster["name"],
                "user": user["name"]
            }
        }
        
        config = {
            "apiVersion": "v1",
            "kind": "Config",
            "preferences":{},
            "clusters": [cluster],
            "contexts": [context],
            "users": [user],
            "current-context": context["name"]
        }
        return config
    
    def stop(self):
        location_params = self.clusters.get_location_params()
        print(location_params)
        request = self.clusters.get_clusters_api().delete(clusterId=self.name, **location_params)
        
        try:
            response = request.execute()
            return Operation(response, self.clusters.get_operations_api(), self.clusters.get_location_params())
        except HttpError as e:
            raise Exception("Failed to stop cluster : %s" % str(e))
            
    def get_node_pools(self):
        location_params = self.get_location_params()
        request = self.get_node_pools_api().list(**location_params)
        
        try:
            response = request.execute()
            node_pools = []
            for elem in response.get("nodePools", []):
                node_pools.append(NodePool(elem["name"], self))
            return node_pools
        except HttpError as e:
            raise Exception("Failed to get node pools : %s" % str(e))
        
    def get_node_pool(self, node_pool_id):
        return NodePool(node_pool_id, self)
    
class Clusters(object):
    def __init__(self, project_id, zone, credentials=None):
        logging.info("Connect using project_id=%s zone=%s credentials=%s" % (project_id, zone, credentials))
        instance_info = get_instance_info()
        if _is_none_or_blank(project_id):
            default_project = instance_info["project"]
            logging.info("No project specified, using {} as default".format(default_project))
            self.project_id = default_project
        else:
            self.project_id = project_id
        if _is_none_or_blank(zone):
            default_zone = instance_info["zone"]
            logging.info("No zone specified, using {} as default".format(default_zone))
            self.zone = default_zone
        else:
            self.zone = zone
        self.service = discovery.build('container', 'v1', credentials=credentials, cache_discovery=False)
        self.compute = discovery.build('compute', 'v1', credentials=credentials, cache_discovery=False)
        
    def get_location(self):
        return "projects/%s/locations/%s" % (self.project_id, self.zone)
        
    def get_location_params(self):
        return {"projectId":self.project_id, "zone":self.zone}
    
    def get_operations_api(self):
        return self.service.projects().zones().operations()
    
    def get_clusters_api(self):
        return self.service.projects().zones().clusters()
    
    def get_instance_groups_api(self):
        return self.compute.instanceGroups()
    
    def new_cluster_builder(self):
        return ClusterBuilder(self)
    
    def get_cluster(self, name):
        return Cluster(name, self)
