# Vi.kram Saraph
# Python library for interacting with geth blockchain

import requests
import sys
import multiprocessing
import random

class StorageMap:
	def __init__(self):
		self.map = {}		# addr -> txn | None
		self.has_write = set()
	def access(self, txn, addr, is_write):
		if addr not in self.map:
			# fresh address
			self.map[addr] = txn
			if is_write:
				self.has_write.add(addr)
			return False	# no conflict
		if self.map[addr] == txn:
			# you are the sole reader/writer
			if is_write:
				self.has_write.add(addr)
			return False
		self.map[addr] = None
		if not is_write and addr not in self.has_write:
			# another read - no conflict
			return False
		return True

class SimEVM:
	def __init__(self, N=64):
		self.aborted = set()	# track aborted txns during execution
		self.storage = StorageMap()		# create simulated storage
		self.processors = [Processor(self.storage) for n in xrange(N)]	# virtual processors
	def run(self):
		pass 

# Processor steps through instructions of given transaction.
# For each SSTORE or SLOAD, write to given StorageMap object.
# If conflict is encountered, stepper should communicate this.
class Processor:
	def __init__(self, storage):
		self.reset()
		self.txn = None
		self.storage = storage
		self.is_active = False
	def reset(self):
		self.pc = 0
		self.gas = 0
		self.gas_used = 0
	def new_transaction(self, txn):
		self.reset()
		self.txn = txn
	def step_instruction(self):
		# first check if txn has finished
		if self.pc >= self.txn.length:
			return "FINISHED"
		# next, check if there is enough gas
		op = self.txn.get_op(self.pc)
		cost = self.txn.get_gas(self.pc)
		if cost <= self.gas:
			self.gas -= cost
			self.gas_used += cost
		else:
			return "NOGAS"
		# now check for SSTORE/SLOAD 
		txn_hash = self.txn.get_hash()
		addr = self.txn.get_addr(self.pc)
		if op in ["SSTORE", "SLOAD"]:
			if op == "SSTORE":
				conf = self.storage.access(txn_hash, addr, True)
			else:
				conf = self.storage.access(txn_hash, addr, False)
			if conf:
				return "ABORTED"
		# move counter up
		self.pc += 1
		return None

	def step(self, stipend):
		# give a small stipend of gas
		# returns either None, "FINISHED", or "ABORTED"
		self.gas += stipend
		# Run until "NOGAS". If "FINISHED" or "ABORTED"
		# is encountered instead, stop and return that value.
		while True:
			ret = self.step_instruction()
			if ret != None:
				break
		if ret == "NOGAS":
			ret = None
		return ret
		

class Transaction:
	def __init__(self, txn_hash, trace):
		self.txn_hash = txn_hash
		self.trace = trace
		self.length = len(trace)
	def get_op(self, pc):
		return self.trace[pc]["op"]
	def get_hash(self):
		return self.txn_hash
	def get_addr(self, pc):
		return (self.trace[pc]["account"], self.trace[pc]["location"])
	def get_gas(self, pc):
		return int(self.trace[pc]["cost"])

# Javascript tracer
# Get gas price of each op, top of stack to determine storage address
# (gasPrice is actually gasCost, geth implementation has a bug)
gas_tracer = """{i: 0, data: [],
	step: function(log) {
		opstr = log.op.toString();
		this.i = this.i + 1;
		if (log.stack.length() == 0) {loc = null; } else {loc = log.stack.peek(0)}
		this.data.push({"op": opstr,
						"account": log.account,
						"location": loc,
						"number": this.i,
						"cost": log.gasPrice});
	},
	result: function() {return this.data; }
	}"""

# Call debug_traceTransaction
def trace_transaction(txn):
	opt = {"tracer": gas_tracer, "timeout": "1h"}
	payload = {"jsonrpc":"2.0", "method":"debug_traceTransaction", "params":[txn, opt], "id": 1}
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()
	print res

	return res["result"]
trace_pool = multiprocessing.Pool(8)

# Get transaction hashes and total gas used
def get_transactions(block):
	payload = {"jsonrpc":"2.0", "method":"eth_getBlockByNumber", "params": [hex(block), True], "id": 1}
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()

	txns = [txn["hash"] for txn in res["result"]["transactions"]]
	gas_used = res["result"]["gasUsed"]
	return txns, gas_used

# Execute a block of transactions in the following way:
# First calculate the trace of each transaction
# Then randomly step through them by selecting a random
# transaction, then stepping forward its program counter by
# a random amount. While doing so, track the storage locations
# written/read by each transaction. If there is a conflict,
# abort the transaction resulting in the conflict.
# Return a set of transactions for deferral.

N = 64		# number of simulated processors
step_size = 5		# max step size
gas_step_size = 5	# max gas step

def execute_block(block):
	# Get transactions (and length of critical path of seq exec)
	txns, seq_crit_len = get_transactions(block)

	# Check whether traces have been computed

	# Compute traces
	traces = trace_pool.map(trace_transaction, txns)

	# Save traces

	# Initialize pool
	


#print trace_transaction("0x90cba76c95b715fbbbc3473f6441a45c5ade78a718de5fd7fde00cf13c254509")
execute_block(4000000)
