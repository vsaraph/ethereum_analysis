# Vi.kram Saraph
# Python library for interacting with geth blockchain

import requests
import sys
import multiprocessing
import random

class storage_map:
	def __init__(self, full=False):
		# map only keeps track of last reader/write
		# accesses stores all read/write info
		self.full = full
		self.map = {}
		self.has_write
		self.accesses = {}
	def access(self, txn, addr, is_write, abort=True):
		if addr not in self.map:
			self.map[addr] = set([txn])
			return False
		else:
			txns = self.map[addr]
			if is_write:
				if type(txns) == type(""):
					if txns == txn:
						return False
					if not abort:
						self.map
					return True

rw_tracer = """{i: 0, data: [],
	step: function(log) {
		opstr = log.op.toString();
		this.i = this.i + 1;
		if (opstr == "SSTORE" || opstr == "SLOAD")
			this.data.push([opstr, log.account, log.stack.peek(0), this.i]);
	},
	result: function() {return this.data; }
	}"""

# Call debug_traceTransaction
def trace_transaction(txn):
	opt = {"tracer": rw_tracer, "timeout": "1h"}
	payload = {"jsonrpc":"2.0", "method":"debug_traceTransaction", "params":[txn, opt], "id": 1}
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()
	print res

	return res["result"]
trace_pool = multiprocessing.Pool(8)

# Get transaction hashes
def get_transactions(block):
	payload = {"jsonrpc":"2.0", "method":"eth_getBlockByNumber", "params": [hex(block), True], "id": 1}
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()

	txns = [txn["hash"] for txn in res["result"]["transactions"]]
	return txns

# Execute a block of transactions in the following way:
# First calculate the trace of each transaction
# Then randomly step through them by selecting a random
# transaction, then stepping forward its program counter by
# a random amount. While doing so, track the storage locations
# written/read by each transaction. If there is a conflict,
# abort the transaction resulting in the conflict.
# Return a set of transactions for deferral.

N = 64		# number of simulated processors
step_size = 5	# max step size

def execute_block(block):
	# Get transactions
	txns = get_transactions(block)

	# Check whether traces have been computed

	# Compute traces
	traces = trace_pool.map(trace_transaction, txns)

	# Save traces

	# Initialize program counters
	pc = N * [0]

	# Initialize pool
	


#print trace_transaction("0x90cba76c95b715fbbbc3473f6441a45c5ade78a718de5fd7fde00cf13c254509")
execute_block(4000000)
