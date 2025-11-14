# Changelog

## Next version 
- Support for enabling Gateway API

## Version 1.4.1 - Feature and bugfix release
- Add DNS endpoint support when attaching clusters
- Improve Nvidia driver installation support

## Version 1.4.0 - Feature and bugfix release
- Add support for release channels on standard clusters
- Add support for GCP labels on nodepools
- Add support for taints on nodepools
- Fix cluster GCP labels
- Miscellaneous UI improvements

## Version 1.3.2
- Fix attaching to existing clusters from another project

## Version 1.3.1
- Fix CIDR block detection and improve descriptions of pod and service IP range fields
- Improve error message when gcloud has not been properly authorized
- Add support for spot VMs

## Version 1.3.0
- Add more supported Python versions. This plugin can now use 2.7 (deprecated), 3.6, 3.7, 3.8, 3.9, 3.10 (experimental), 3.11 (experimental)
- Fix issue when creating a cluster in a different region/zone

## Version 1.2.0
- Fix the cluster configuration's merging mechanism for string parameters
- Remove support for legacy authorization (ABAC)
- Authentication for `kubectl` command now relies on `gke-gcloud-auth-plugin` as this is the only supported mode starting with Kubernetes 1.26 (see [documentation](https://cloud.google.com/blog/products/containers-kubernetes/kubectl-auth-changes-in-gke)).
/!\ if you're using a DSS version prior 11.4, you'll have to install `gke-gcloud-auth-plugin` manually (see the link above)

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
