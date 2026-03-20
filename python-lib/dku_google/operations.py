from google.cloud import container_v1

import os, sys, json, time
import logging

class Operation(object):
    def __init__(self, operation, operations_client, parent_location):
        self.operation = operation
        if hasattr(operation, "name"):
            self.operation_id = operation.name
        else:
            self.operation_id = operation["name"]
        self.operations_client = operations_client
        self.parent_location = parent_location

    def _get_operation_name(self):
        if self.operation_id.startswith("projects/"):
            return self.operation_id
        return "%s/operations/%s" % (self.parent_location, self.operation_id)
        
    def _refresh(self):
        self.operation = self.operations_client.get_operation(name=self._get_operation_name())
        
    def is_done(self):
        if hasattr(self.operation, "status"):
            return self.operation.status == container_v1.Operation.Status.DONE
        return self.operation.get("status", "") == "DONE"
    
    def wait_done(self):
        while not self.is_done():
            time.sleep(5)
            self._refresh()
