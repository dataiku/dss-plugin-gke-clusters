# Managed GKE clusters plugin

This plugin allows to dynamically create, manage and scale GKE clusters in DSS.

Requires DSS 6.0 or above.

For more details, please see [the DSS reference documentation](https://doc.dataiku.com/dss/latest/containers/gke/index.html).

## Release notes

### v1.1.2
- Fix string encoding issues in test network connectivity macro

### v1.1.1
- Fix `Test network connectivity` macro when the hostname is already an IP.

### v1.1.0

- Clusters are now reusing the DSS host's VPC and subnetwork by default (can be changed by unticking the related parameter). Requires the `compute.zones.list` IAM permission.
- Kubernetes labels can be defined for each node pool
- Default service account running on nodes can be changed to a custom value or be inherited from the DSS host. Requires the `iam.serviceAccountUser` IAM permission

### v1.0.1

- Clusters created from the plugin are now VPC-native by default.
