import time

class Operation(object):
    def __init__(self, operation, operations, location_data):
        self.operation = operation
        self.operation_id = operation["name"]
        self.operations = operations
        if 'region' in location_data:
            # the regional api uses the 'name' arg, not the old projectId/zone/... ones
            location_data = {"name": 'projects/%s/locations/%s/operations/%s' % (location_data['projectId'], location_data['region'], self.operation_id)}
        self.location_data = location_data
        
    def _refresh(self):
        self.operation = self.operations.get(operationId=self.operation_id, **self.location_data).execute()
        
    def is_done(self):
        return self.operation.get('status', '') == 'DONE'
    
    def wait_done(self):
        while not self.is_done():
            time.sleep(5)
            self._refresh()
