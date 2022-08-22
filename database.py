# Vikram Saraph
# Trace transactions and store resulting traces in a SQLite3 database.

# This script assumes you have a SQLite3 DB set up. See traces.sql for
# the schema used. The script also assumes you have an archive node
# of geth running in the background, with the debug RPC API enabled.
# Note that you MUST being running an archive node (i.e. --syncmode=full)
# for geth's tracer to work.

# geth's traceTransaction returns traces that are Base64 encoded.
# Accordingly, this script stores the Base64 encoded traces as strings.

# Database and geth endpoint configuration are located in trace_config.yml.

import base64
import json
import os
import sqlite3
import sys
import yaml

config = yaml.safe_load(open("config.yml"))
db_file = os.path.expanduser(config["db_file"])

class Database:
    def __init__(self):
        self.connection = sqlite3.connect(db_file)
    
    def decode_trace(self, base64_trace_string):
        return json.loads(base64.b64decode(base64_trace_string))

    # Check whether block (and its transactions' traces) are in the database
    def block_exists(self, block):
        cursor = self.connection.cursor()
        cursor.execute("SELECT block FROM block WHERE block = ?", (block,))
        
        if not cursor.fetchone():
            result = False
        else:
            result = True
        cursor.close()
        return result

    # Load and decode traces in a given block
    def load_block(self, block):
        cursor = self.connection.cursor()
        cursor.execute("SELECT hash, trace FROM txn WHERE block = ?", (block,))

        traces = {rec[0]: self.decode_trace(rec[1]) for rec in cursor.fetchall()}
        cursor.close()
        return traces

    # Store traces of transactions in a given block
    def store_block(self, block, traces):
        cursor = self.connection.cursor()
        if self.block_exists(block):
            cursor.close()
            return
        cursor.execute("INSERT INTO block VALUES (?)", (block,))

        for txn_hash, trace in traces.items():
            trace_string = base64.b64encode(json.dumps(trace))
            cursor.execute("INSERT INTO txn VALUES (?, ?, ?)", (block, txn_hash, trace_string))

        self.connection.commit()
        cursor.close()

    def close(self):
        self.connection.close()


if __name__ == "__main__":
    db = Database()
    
    sample_block = -1
    db.store_block(sample_block, {-1: "eyJ0ZXN0IjogInRlc3QifQ=="})
    
    if not db.block_exists(sample_block):
        print("Block does not exist!")
        sys.exit(1)
    
    print("Block exists!")
    for txn_hash, trace in db.load_block(sample_block).items():
        print(txn_hash, trace)

