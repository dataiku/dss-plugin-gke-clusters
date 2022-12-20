# Changelog

## Next version
- Fix the cluster configuration's merging mechanism for string parameters
- Remove support for legacy authorization (ABAC)

##  Version 1.1.5 - Feature and bugfix release
- Fix action "Add node pool"
- Change default value for "Inherit DSS host settings" when creating a cluster
- Change default value for "Service account type" in the nodes pool creation form
- Handle regional clusters

## Version 1.1.4 - Feature release
- Add ability to use named secondary ranges
- Add network tags on cluster nodes

## Version 1.1.3 - Internal release
- Fix unicode remnants in `Test network connectivity` macro
- Fix subprocess incompatibilities with Python 3

## Version 1.1.2
- Fix string encoding issues in `Test network connectivity` macro

## Version 1.1.1
- Fix `Test network connectivity` macro when the hostname is already an IP.

## Version 1.1.0
- Clusters are now reusing the DSS host's VPC and subnetwork by default (can be changed by unticking the related parameter). Requires the `compute.zones.list` IAM permission.
- Kubernetes labels can be defined for each node pool
- Default service account running on nodes can be changed to a custom value or be inherited from the DSS host. Requires the `iam.serviceAccountUser` IAM permission

## Version 1.0.1
- Clusters created from the plugin are now VPC-native by default.
