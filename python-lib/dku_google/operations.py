from googleapiclient import discovery
from googleapiclient.errors import HttpError

import os, sys, json, time
import logging

class Operation(object):
    def __init__(self, operation, operations, location_data):
        self.operation = operation
        self.operations = operations
        self.location_data = location_data
        self.operation_id = operation["name"]
        
    def _refresh(self):
        self.operation = self.operations.get(operationId=self.operation_id, **self.location_data).execute()
        
    def is_done(self):
        return self.operation.get('status', '') == 'DONE'
    
    def wait_done(self):
        while not self.is_done():
            time.sleep(5)
            self._refresh()
