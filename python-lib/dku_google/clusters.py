from googleapiclient import discovery
from six import text_type
from googleapiclient.errors import HttpError
from dku_google.gcloud import get_sdk_root, get_access_token_and_expiry, get_instance_info
from dku_google.gcloud import get_instance_network, get_instance_service_account
from dku_utils.access import _has_not_blank_property, _is_none_or_blank, _default_if_blank, _merge_objects

import os, sys, json, re, random
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
        self.use_spot_vms = False
        self.service_account = None
        self.nodepool_labels = {}
        self.nodepool_taints = []
        self.nodepool_gcp_labels = {}
        self.nodepool_tags = []
 
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

    def with_spot_vms(self, use_spot_vms):
        self.use_spot_vms = use_spot_vms
        return self

    def with_nodepool_labels(self, nodepool_labels=[]):
        if any(not label.get("from", "") for label in nodepool_labels):
            raise ValueError("Some of the cluster key-value label pairs have no key and thus are invalid")

        if nodepool_labels:
            nodepool_labels_dict = {label["from"]: label.get("to", "") for label in nodepool_labels}
            logging.info("Adding labels {} to node pool {}".format(nodepool_labels_dict, self.name))
            self.nodepool_labels.update(nodepool_labels_dict)
        return self
    
    def with_nodepool_taints(self, nodepool_taints=[]):
        if nodepool_taints:
            logging.info("Adding taints {} to node pool {}".format(nodepool_taints, self.name))
            self.nodepool_taints.extend(nodepool_taints)
        return self

    def with_nodepool_gcp_labels(self, nodepool_gcp_labels={}, cluster_formatted_labels=[]):
        if any(nodepool_gcp_labels, lambda label: not label.get("from", "")):
            raise ValueError("Some of the cluster key-value label pairs have no key and thus are invalid: %s" % nodepool_gcp_labels)

        if cluster_formatted_labels:
            logging.info("Adding cluster labels {} to node pool {}".format(cluster_formatted_labels, self.name))
            self.nodepool_gcp_labels.update(cluster_formatted_labels)

        if nodepool_gcp_labels:
            logging.info("Adding labels {} to node pool {}".format(nodepool_gcp_labels, self.name))
            self.nodepool_gcp_labels.update(nodepool_gcp_labels)
        return self

    def with_nodepool_tags(self, nodepool_tags=[]):
        if nodepool_tags:
            logging.info("Adding network tags {} to node pool {}".format(nodepool_tags, self.name))
            for tag in nodepool_tags:
                self.nodepool_tags.append(tag)
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
        if self.use_spot_vms:
            node_pool['config']['spot'] = True
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
        node_pool["config"]["taints"] = self.nodepool_taints
        node_pool["config"]["resourceLabels"] = self.nodepool_gcp_labels
        node_pool["config"]["tags"] = self.nodepool_tags
            
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
        self.http_load_balancing = None
        self.node_pools = []
        self.is_regional = False
        self.locations = []
        self.is_autopilot = False
        self.release_channel = 'STABLE'
        self.settings_valve = None
       
    def with_name(self, name):
        self.name = name
        return self
    
    def with_version(self, version):
        self.version = version
        return self
    
    def with_autopilot(self, is_autopilot, release_channel):
        self.is_autopilot = is_autopilot
        self.release_channel = release_channel
        return self
    
    def with_regional(self, is_regional, locations=[]):
        self.is_regional = is_regional
        self.locations = locations
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
        if any(not label.get("from", "") for label in labels):
            raise ValueError("Some of the cluster key-value label pairs have no key and thus are invalid")

        labels = {label["from"]: label.get("to", "") for label in labels}
        self.labels.update(labels)
        if self.labels:
            logging.info("Adding labels {}".format(str(self.labels)))
        return self

    def with_vpc_native_settings(self, is_vpc_native, pod_ip_range, svc_ip_range):
        if is_vpc_native:
            self.is_vpc_native = is_vpc_native
            if pod_ip_range is not None and len(pod_ip_range) > 0 and pod_ip_range == svc_ip_range:
                raise Exception("Service IP range must be different from pod IP range")
            self.pod_ip_range = pod_ip_range
            self.svc_ip_range = svc_ip_range
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
            }
        }
        if self.is_regional:
            create_cluster_request_body["parent"] = self.clusters.get_regional_location()
            if len(self.locations) > 0:
                create_cluster_request_body["cluster"]["locations"] = self.locations
        else:
            create_cluster_request_body["parent"] = self.clusters.get_zonal_location()
            
        if self.is_vpc_native:
            ip_allocation_policy = {
                "createSubnetwork": False,
                "useIpAliases": True
            }
            # Should match both a.b.c.d/e and /e
            range_regex = '^([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)?/[0-9]+$'
            if re.match(range_regex, cluster_svc_ip_range):
                ip_allocation_policy["servicesIpv4CidrBlock"] = cluster_svc_ip_range
            elif cluster_svc_ip_range is not None and len(cluster_svc_ip_range) > 0:
                # assume it's an existing range name (shared VPC case)
                ip_allocation_policy["servicesSecondaryRangeName"] = cluster_svc_ip_range
            if re.match(range_regex, cluster_pod_ip_range):
                ip_allocation_policy["clusterIpv4CidrBlock"] = cluster_pod_ip_range
            elif cluster_pod_ip_range is not None and len(cluster_pod_ip_range) > 0:
                # assume it's an existing range name (shared VPC case)
                ip_allocation_policy["clusterSecondaryRangeName"] = cluster_pod_ip_range
            create_cluster_request_body["cluster"]["ipAllocationPolicy"] = ip_allocation_policy
        
        create_cluster_request_body["cluster"]["addonsConfig"] = {}
        if self.http_load_balancing or self.is_autopilot:
            create_cluster_request_body["cluster"]["addonsConfig"]["httpLoadBalancing"] = {"disabled":False}
        else:
            create_cluster_request_body["cluster"]["addonsConfig"]["httpLoadBalancing"] = {"disabled":True}

        for node_pool in self.node_pools:
            create_cluster_request_body['cluster']['nodePools'].append(node_pool)
            
        if self.is_autopilot:
            create_cluster_request_body['cluster']['autopilot'] = {"enabled":True}
            create_cluster_request_body['cluster']['releaseChannel'] = {"channel":self.release_channel}
            
        if not _is_none_or_blank(self.settings_valve):
            valve = json.loads(self.settings_valve)
            create_cluster_request_body["cluster"] = _merge_objects(create_cluster_request_body["cluster"], valve)
                
        logging.info("Requesting cluster %s" % json.dumps(create_cluster_request_body, indent=2))
                
        if self.is_regional:
            location_params = {"parent" : self.clusters.get_regional_location()}
            request = self.clusters.get_regional_clusters_api().create(body=create_cluster_request_body, **location_params)

            try:
                response = request.execute()
                return Operation(response, self.clusters.get_regional_operations_api(), self.clusters.get_regional_location_params())
            except HttpError as e:
                raise Exception("Failed to create cluster : %s" % str(e))
        else:
            location_params = self.clusters.get_zonal_location_params()
            request = self.clusters.get_zonal_clusters_api().create(body=create_cluster_request_body, **location_params)

            try:
                response = request.execute()
                return Operation(response, self.clusters.get_zonal_operations_api(), self.clusters.get_zonal_location_params())
            except HttpError as e:
                raise Exception("Failed to create cluster : %s" % str(e))
    
class NodePool(object):
    def __init__(self, name, cluster):
        self.name = name
        self.cluster = cluster
        
    def get_location_params(self):
        # the zonal and regional APIs don't have the same args, and notably the zonal API
        # is a bit braindead in that if has args that are both deprecated and required
        # despite their replacement arg being possible...
        if self.cluster.definition_level == 'zonal':
            location_params = self.cluster.get_location_params()
            location_params['nodePoolId'] = self.name
            return location_params
        else:
            return {'name':"%s/nodePools/%s" % (self.cluster.get_location(), self.name)}
        
    def get_info(self):
        request = self.cluster.get_node_pools_api().get(**self.get_location_params())
        response = request.execute()
        return response
    
    def get_instance_groups_info(self):
        node_pool_info = self.get_info()
        instance_groups = []
        for instance_group_url in node_pool_info.get("instanceGroupUrls", []):
            # the zone should be fetched from the url, since regional clusters will have
            # instance groups in several zones
            m = re.match("^.*/([^/]+)/[^/]+/([^/]+)", instance_group_url)
            instance_group_zone = m.group(1)
            instance_group_name = m.group(2)
            location_params = self.cluster.get_parent_location_params()
            # the parameter is named 'project' and not 'projectId', hurray for consistency
            clean_location_params = {'project':location_params.get('projectId', None)}
            # put the right zone in (might not be the cluster's)
            clean_location_params["zone"] = instance_group_zone
            logging.info("get_instance_groups_api %s  %s" % (instance_group_name, str(clean_location_params)))
            request = self.cluster.get_instance_groups_api().get(instanceGroup=instance_group_name, **clean_location_params)
            instance_groups.append(request.execute())
        return instance_groups
        
    def resize(self, num_nodes):
        resize_cluster_request_body = {
            "nodeCount" : num_nodes
        }

        request = self.cluster.get_node_pools_api().setSize(body=resize_cluster_request_body, **self.get_location_params())
        try:
            response = request.execute()
            return Operation(response, self.cluster.get_operations_api(), self.cluster.get_parent_location_params())
        except HttpError as e:
            raise Exception("Failed to resize node pool : %s" % str(e))
        
    def delete(self):
        request = self.cluster.get_node_pools_api().delete(**self.get_location_params())
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
                
        parent_location_params = self.cluster.get_location_params()
        # it's a creation, so the locations are passed as 'parent' and not 'name' (for regional clusters)
        if 'name' in parent_location_params:
            parent_location_params = {'parent':parent_location_params['name']}
        request = self.cluster.get_node_pools_api().create(body=create_node_pool_request_body, **parent_location_params)
        
        try:
            response = request.execute()
            return Operation(response, self.cluster.get_operations_api(), self.cluster.get_parent_location_params())
        except HttpError as e:
            raise Exception("Failed to create node pool : %s" % str(e))

class Cluster(object):
    def __init__(self, name, definition_level, clusters):
        self.name = name
        self.clusters = clusters
        self.definition_level = definition_level
        logging.info("Cluster object named %s of level %s" % (name, definition_level))
        
    def get_location(self):
        if self.definition_level == 'zonal':
            return "%s/clusters/%s" % (self.clusters.get_zonal_location(), self.name)
        else:
            return "%s/clusters/%s" % (self.clusters.get_regional_location(), self.name)
        
    def get_parent_location_params(self):
        if self.definition_level == 'zonal':
            return self.clusters.get_zonal_location_params()
        else:
            return self.clusters.get_regional_location_params()
            
    def get_location_params(self):
        if self.definition_level == 'zonal':
            params = self.get_parent_location_params().copy()
            params["clusterId"] = self.name
            return params
        else:
            return {"name":self.get_location()}
    
    def get_clusters_api(self):
        if self.definition_level == 'zonal':
            return self.clusters.get_zonal_clusters_api()
        else:
            return self.clusters.get_regional_clusters_api()
    
    def get_node_pools_api(self):
        return self.get_clusters_api().nodePools()
    
    def get_operations_api(self):
        if self.definition_level == 'zonal':
            return self.clusters.get_zonal_operations_api()
        else:
            return self.clusters.get_regional_operations_api()
                    
    def get_instance_groups_api(self):
        return self.clusters.get_instance_groups_api()
        
    def get_info(self):
        location_params = self.get_location_params()
        request = self.get_clusters_api().get(**location_params)
        response = request.execute()
        return response

    def stop(self):
        location_params = self.get_location_params()
        request = self.get_clusters_api().delete(**location_params)
        
        try:
            response = request.execute()
            return Operation(response, self.get_operations_api(), self.get_parent_location_params())
        except HttpError as e:
            raise Exception("Failed to stop cluster : %s" % str(e))
            
    def get_node_pools(self):
        location_params = self.get_location_params()
        if 'name' in location_params:
            # for the list() call, the cluster is not the name, but the parent (logically)
            location_params['parent'] = location_params['name']
            del location_params['name']
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
    def __init__(self, project_id, zone, region, credentials=None):
        logging.info("Connect using project_id=%s zone=%s region=%s credentials=%s" % (project_id, zone, region, credentials))
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
        if _is_none_or_blank(region):
            default_region = '-'.join(self.zone.split("-")[:-1])
            logging.info("No region specified, using {} as default".format(default_region))
            self.region = default_region
        else:
            self.region = region
        self.service = discovery.build('container', 'v1', credentials=credentials, cache_discovery=False)
        self.compute = discovery.build('compute', 'v1', credentials=credentials, cache_discovery=False)
        
    def get_zonal_location(self):
        return "projects/%s/locations/%s" % (self.project_id, self.zone)
        
    def get_zonal_location_params(self):
        return {"projectId":self.project_id, "zone":self.zone}
    
    def get_zonal_operations_api(self):
        return self.service.projects().zones().operations()
    
    def get_zonal_clusters_api(self):
        return self.service.projects().zones().clusters()
        
    def get_regional_location(self):
        return "projects/%s/locations/%s" % (self.project_id, self.region)
        
    def get_regional_location_params(self):
        return {"projectId":self.project_id, "region":self.region}
    
    def get_regional_operations_api(self):
        return self.service.projects().locations().operations()
    
    def get_regional_clusters_api(self):
        return self.service.projects().locations().clusters()
    
    def get_instance_groups_api(self):
        return self.compute.instanceGroups()
    
    def new_cluster_builder(self):
        return ClusterBuilder(self)
    
    def get_cluster(self, name, definition_level='zonal'):
        return Cluster(name, definition_level, self)
