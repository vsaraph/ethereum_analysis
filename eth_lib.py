# Vi.kram Saraph
# Python library for interacting with geth blockchain

import requests
import sys
import multiprocessing
import random
import base64
import json
import getpass.getpass()

db_server = "db.cs.brown.edu"
db_name = "ethereum_traces"
username = "vsaraph"
password = getpass.getpass()

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
	def __init__(self, txns, N=64):
		self.txns = txns		# list of txns (Transaction objects) to execute
		self.n_proc = min(N, len(txns))		# number of processors

		self.txn_gas = {txn.txn_hash: txn.total_gas() for txn in txns}
		self.aborted_gas = {}	# gas used by txn before aborting
		self.finished = set()	# txns that execute to completion

		self.storage = StorageMap()		# create simulated storage
		self.processors = [Processor(self.storage) for n in xrange(self.n_proc)]	# virtual processors
		self.stipend = 100		# amount of gas process is given to continue its execution

		# randomize order of transactions
		random.shuffle(txns)
	def run(self):
		# Initialize processors
		for proc in self.processors:
			txn = self.txns.pop(0)
			proc.new_transaction(txn)

		# End when there are no more running processors
		N = self.n_proc
		while self.processors:
			n = random.randrange(N)
			proc = self.processors[n]
			ret = proc.step(self.stipend)
			# if process is not done, choose another
			if not ret:
				continue

			# get gas used
			txn_hash = proc.txn.get_hash()
			gas_used = proc.get_gas_used()
			if ret == "FINISHED":
				#print "Transaction %s finished with %d" % (txn_hash, gas_used)
				self.finished.add(txn_hash)
			elif ret == "ABORTED":
				#print "Transaction %s aborted with %d" % (txn_hash, gas_used)
				self.aborted_gas[txn_hash] = gas_used

			# replace txn or delete process
			if self.txns:
				new_txn = self.txns.pop(0)
				proc.new_transaction(new_txn)
			else:
				del self.processors[n]
				N -= 1

	def parallel_work(self):
		# append 0 so that max is defined on empty list
		return max([0] + [self.txn_gas[txn_hash] for txn_hash in self.finished])

	def sequential_work(self):
		return sum(self.aborted_gas.values())

	def total_work(self):
		return sum(self.txn_gas.values())


# Processor steps through instructions of given transaction.
# For each SSTORE or SLOAD, write to given StorageMap object.
# If conflict is encountered, stepper should communicate this.
class Processor:
	def __init__(self, storage):
		self.reset()
		self.storage = storage
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
		cost = self.txn.get_gas_at(self.pc)
		if cost <= self.gas:
			self.gas -= cost
			self.gas_used += cost
			#print "Gas used by transaction %s: %s\t%d" % (self.txn.get_hash(), op, cost)
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

	def get_gas_used(self):
		return self.gas_used
		

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
	# Change this function when gasCost field is fixed
	# Currently, CALL gasCost is way off
	def get_gas_at(self, pc):
		if pc >= self.length - 1:
			return 0
		return int(self.trace[pc]["gas_left"]) - int(self.trace[pc+1]["gas_left"])
		#return self.trace[pc]["cost"]
	def total_gas(self):
		if not self.trace:
			return 0
		return self.trace[0]["gas_left"] - self.trace[-1]["gas_left"]

# namespace
# could define all methods as static
class EVMStats:
	# take evm that has already executed, and calculate numbers
	def __init__(self, evm):
		self.evm = evm

	def stats_formatted(self):
		# percentage aborts
		aborts = len(self.evm.aborted_gas)
		total_txns = len(self.evm.txn_gas)
		
		if total_txns != 0:
			percentage = float(aborts) / total_txns
		else:
			percentage = float('nan')

		# crit path
		seq_work = self.evm.sequential_work()
		para_work = self.evm.parallel_work()
		total_work = self.evm.total_work()
		conc_work = seq_work + para_work

		if conc_work != 0:
			speedup = total_work / conc_work
		else:
			speedup = float('nan')

		# return formatted str
		format_str = "%d\t%d\t%0.2f\t%d\t%d\t%d\t%0.2f"
		stats = (aborts, total_txns, percentage)
		stats += (seq_work, para_work, total_work, speedup)
		return format_str % stats

# get gas used by transaction
# (this information is not provided in txn objects returned by getBlockByHash)
def gas_used_by_transaction(txn):
	payload = {"jsonrpc":"2.0", "method":"eth_getTransactionReceipt", "params":[txn]}
	req = requests.post("https://127.0.0.1:8545", json = payload)
	res = req.json()

	return int(res["result"]["gasUsed"], 16)

# Javascript tracer
# Get gas price of each op, top of stack to determine storage address
gas_tracer = """{i: 0, data: [],
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

# default tracer
def trace_transaction_default(txn):
	opt = {"disableStorage": True, "disableMemory": True, "disableStack":True, "timeout": "1h"}
	payload = {"jsonrpc":"2.0", "method":"debug_traceTransaction", "params":[txn, opt], "id": 1}
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()
	return res["result"]

# Call debug_traceTransaction with custom tracer
def trace_transaction(txn):
	opt = {"tracer": gas_tracer, "timeout": "1h"}
	payload = {"jsonrpc":"2.0", "method":"debug_traceTransaction", "params":[txn, opt], "id": 1}
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()

	ret = json.loads(base64.b64decode(res["result"]))
	#print ret
	return ret
trace_pool = multiprocessing.Pool(16)

# Get transaction hashes and total gas used
def get_transactions(block):
	payload = {"jsonrpc":"2.0", "method":"eth_getBlockByNumber", "params": [hex(block), True], "id": 1}
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()

	txns = [txn["hash"] for txn in res["result"]["transactions"]]
	return txns

class DBWrapper:
	def __init__(self):
		pass
	def exists(self, block):
		pass
	def get_trace(self, block):
		pass
	def save_trace(self, block):
		pass

# Execute a block of transactions in the following way:
# First calculate the trace of each transaction
# Then randomly step through them by selecting a random
# transaction, then stepping forward its program counter by
# a random amount. While doing so, track the storage locations
# written/read by each transaction. If there is a conflict,
# abort the transaction resulting in the conflict.
# Return a set of transactions for deferral.

class Main:
	def __init__(self):
		random.seed()
		self.freq = 10
		open("output.txt", "w").close()

	def execute_block(self, block):
		# Get transactions (and length of critical path of seq exec)
		txns = get_transactions(block)

		# (TODO) Check whether traces have been computed

		# Compute traces
		traces = trace_pool.map(trace_transaction, txns)

		# (TODO) Save traces

		# Create Transaction objects
		txn_objects = []
		for i, txn in enumerate(txns):
			txn_objects.append(Transaction(txn, traces[i]))

		# Create and run EVM
		evm = SimEVM(txn_objects)
		evm.run()

		# get stats and print
		stats = EVMStats(evm)
		formatted = stats.stats_formatted()

		f = open("output.txt", "a")
		f.write(str(block) + '\t' + formatted + '\n')
		f.close()

	def execute_range(self, start_block, end_block):
		for block in xrange(start_block, end_block, self.step):
			self.execute_block(block)

#print trace_transaction("0x90cba76c95b715fbbbc3473f6441a45c5ade78a718de5fd7fde00cf13c254509")
#tr = trace_transaction2("0xe5c0b9656aba44735008202d975dd4f9ca07db5e7b2ec4611d63237fd45974b0")
#for rec in tr["structLogs"]:
#	print rec
#	if rec["op"] == "CALL":
#		print "@o@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
m = Main()
#m.execute_block(4530000)
m.execute_range(4530000, 4570000)
