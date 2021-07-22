PLUGIN_VERSION=1.1.3
PLUGIN_ID=gke-clusters

plugin:
	cat plugin.json|json_pp > /dev/null
	rm -rf dist
	mkdir dist
	zip --exclude "*.pyc" -r dist/dss-plugin-${PLUGIN_ID}-${PLUGIN_VERSION}.zip plugin.json code-env parameter-sets python-clusters python-lib python-runnables
