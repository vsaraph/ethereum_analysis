# Vikram Saraph
# Trace transactions and store resulting traces in a SQLite3 database.

# This script assumes you have a SQLite3 DB set up. See traces.sql for
# the assumed schema. The script also assumes you have an archive node
# of geth running in the background, with the debug RPC API enabled.
# Note that you MUST being running an archive node (i.e. --syncmode=full)
# for geth's tracer to work.

# Database and geth endpoint configuration are located in trace_config.yml.

from database import Database
import pathos
import requests
import yaml

config = yaml.safe_load(open("config.yml"))
geth_json_rpc_endpoint = config["geth_json_rpc_endpoint"]

# (TODO) Just prints for now
# Change this later to use an actual logger
class Logger:
    def log(self, line):
        print line

class Tracer:
    def __init__(self):
        self.process_pool = pathos.pools.ProcessPool()
        self.logger = Logger()
        self.db = Database()
        self.endpoint = geth_json_rpc_endpoint
        
        # geth supports custom JavaScript tracers
        # (TODO) move this to a config file later?
        self.geth_tracer = """{i: 0, data: [],
            step: function(log) {
            opstr = log.op.toString();
            this.i = this.i + 1;
            if (log.stack.length() == 0) {loc = null; } else {loc = log.stack.peek(0)}
            this.data.push({"op": opstr,
            "account": toHex(log.contract.getAddress()),
            "location": loc,
            "number": this.i,
            "cost": log.getCost(),
            "gas_left": log.getGas()});
            },
            result: function() {return this.data; },
            fault: function() {}
            }"""
    
    # Given transaction hash, invoke tracer and return Base64 response string
    def trace_transaction(self, txn_hash):
        self.logger.log("Tracing %s\n" % txn_hash)
        options = {"tracer": self.geth_tracer, "timeout": "1h"}
        payload = {"jsonrpc":"2.0", "method":"debug_traceTransaction", "params":[txn_hash, options], "id": 1}
        request = requests.post(self.endpoint, json=payload)
        response = request.json()
        print response
        return response["result"]

    def get_transactions(self, block):
        payload = {"jsonrpc":"2.0", "method":"eth_getBlockByNumber", "params": [hex(block), True], "id": 1}
        request = requests.post(self.endpoint, json = payload)
        response = request.json()

        txn_hashes = [txn["hash"] for txn in response["result"]["transactions"]]
        return txn_hashes

    def trace_and_store_block(self, block):
        txn_hashes = self.get_transactions(block)
        traces = self.process_pool.map(self.trace_transaction, txn_hashes)
        base64_trace_strings = {txn_hashes[i]: traces[i] for i in xrange(len(txn_hashes))}
        self.db.store_block(block, base64_trace_strings)

if __name__ == "__main__":
    tr = Tracer()
    # 46147 contains the first Ethereum transaction
    for b in xrange(525700, 525710):
        print b
        print tr.trace_and_store_block(b)

