# Vikram Saraph
# Python library for interacting with geth blockchain

import requests
import sys
import multiprocessing
import random
import base64
import json
import sqlite3
import os
import glob

db_name = "/data/ethereum/ethereum_traces.db"

class DataDir:
	def __init__(self, path):
		self.path = path
		if path[-1] != '/' or not os.path.exists(path):
			raise IOError
		self.clear()

	# create and return new file handle
	def new_file(self, name):
		return open(self.path + name, 'w')

	# clear all files
	def clear(self):
		files = glob.glob(self.path + '*')
		#for f in files:
		#	os.remove(f)

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
	def __init__(self, block, txns, is_gas=False, N=64):
		self.is_gas = is_gas	# running simulation using gas vs # of steps

		self.block = block
		self.txns = txns		# list of txns (Transaction objects) to execute
		self.n_proc = min(N, len(txns))		# number of processors

		# saves total costs based on whether
		# we are calculating gas or # instructions
		self.txn_fuel = {}
		for txn in txns:
			txn_hash = txn.txn_hash
			if is_gas:
				self.txn_fuel[txn_hash] = txn.total_gas()
			else:
				self.txn_fuel[txn_hash] = txn.total_inst()
		self.save_message_calls()

		self.aborted = set()	# txns aborted
		self.finished = set()	# txns that execute to completion

		self.storage = StorageMap()		# create simulated storage
		self.processors = [Processor(self.storage, is_gas) for n in xrange(self.n_proc)]	# virtual processors
		self.proc_ids = range(self.n_proc)
		self.stipend = 100 if is_gas else 5		# amount of gas process is given to continue its execution

		# randomize order of transactions
		random.shuffle(txns)
	def run(self):
		# Initialize processors
		for proc in self.processors:
			txn = self.txns.pop(0)
			proc.new_transaction(txn)

		# End when there are no more running processors
		while self.proc_ids:
			n = random.choice(self.proc_ids)
			proc = self.processors[n]
			ret = proc.step(self.stipend)
			# if process is not done, choose another
			if not ret:
				continue

			# update numbers
			txn_hash = proc.txn.get_hash()
			if ret == "FINISHED":
				#print "Transaction %s finished with %d" % (txn_hash, gas_used)
				self.finished.add(txn_hash)
				proc.update_lifetime()
			elif ret == "ABORTED":
				#print "Transaction %s aborted with %d" % (txn_hash, gas_used)
				self.aborted.add(txn_hash)
				proc.update_lifetime()

			# replace txn or delete process
			if self.txns:
				new_txn = self.txns.pop(0)
				proc.new_transaction(new_txn)
			else:
				self.proc_ids.remove(n)

	def parallel_work(self):
		# append 0 so that max is defined on empty list
		return max([0] + [proc.get_lifetime() for proc in self.processors])

	def sequential_work(self):
		return sum([self.txn_fuel[txn_hash] for txn_hash in self.aborted])

	def total_work(self):
		return sum(self.txn_fuel.values())

	# histories of all processors (for gantt charts)
	def get_histories(self):
		return [proc.get_history() for proc in self.processors]

	def save_message_calls(self):
		self.message_calls = 0
		for txn in self.txns:
			if txn.trace:
				self.message_calls += 1


# Processor steps through instructions of given transaction.
# For each SSTORE or SLOAD, write to given StorageMap object.
# If conflict is encountered, stepper should communicate this.
# Can measure work using gas or # of instructions
# `fuel` is either gas or instruction count
class Processor:
	def __init__(self, storage, is_gas=False):
		# 'fuel' refers to either gas or instruction count
		self.is_gas = is_gas
		self.reset()
		self.storage = storage
		self.lifetime_work = 0
		self.work_history = []	# list of inst per txn
	def reset(self):
		# don't reset lifetime_work
		self.pc = 0
		self.fuel = 0	# gas | instruction count
		self.work_done = 0
	def new_transaction(self, txn):
		self.reset()
		self.txn = txn
	def step_instruction(self):
		# first check if txn has finished
		if self.pc >= self.txn.length:
			return "FINISHED"

		# next, check if there is enough gas
		op = self.txn.get_op(self.pc)
		if self.is_gas:
			cost = self.txn.get_gas_at(self.pc)
		else:
			cost = 1

		if cost <= self.fuel:
			self.fuel -= cost
			self.work_done += cost
		else:
			return "NOFUEL"

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
		# give a small stipend of fuel
		# returns either None, "FINISHED", or "ABORTED"
		self.fuel += stipend
		# Run until "NOFUEL". If "FINISHED" or "ABORTED"
		# is encountered instead, stop and return that value.
		while True:
			ret = self.step_instruction()
			if ret != None:
				break
		if ret == "NOFUEL":
			ret = None
		return ret

	# update total work done by processor
	# and add work for sinle txn to history
	def update_lifetime(self):
		self.lifetime_work += self.work_done
		self.work_history.append(self.work_done)
	
	def get_lifetime(self):
		return self.lifetime_work

	# return history (for making gantt charts)
	def get_history(self):
		return self.work_history

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
	def total_gas(self):
		if not self.trace:
			return 0
		return self.trace[0]["gas_left"] - self.trace[-1]["gas_left"]
	def total_inst(self):
		return len(self.trace)

# namespace
# could define all methods as static
class EVMStats:
	# take evm that has already executed, and calculate numbers
	def __init__(self, evm, gantt_dir = "/home/vsaraph/ethereum_analysis/gantt_data/"):
		self.evm = evm
		self.gantt_dir = DataDir(gantt_dir)

	def stats_formatted(self):
		# percentage aborts
		aborts = len(self.evm.aborted)
		total_txns = len(self.evm.txn_fuel)
		message_calls = self.evm.message_calls
		
		if total_txns != 0:
			percentage = float(aborts) / total_txns
		else:
			percentage = float('nan')

		if message_calls != 0:
			percentage_mc = float(aborts) / message_calls
		else:
			percentage_mc = float('nan')

		# crit path
		seq_work = self.evm.sequential_work()
		para_work = self.evm.parallel_work()
		total_work = self.evm.total_work()
		conc_work = seq_work + para_work

		if conc_work != 0:
			speedup = float(total_work) / conc_work
		else:
			speedup = float('nan')

		# return formatted str
		format_str = "%d\t%d\t%0.2f\t%d\t%0.2f\t%d\t%d\t%d\t%0.2f"
		stats = (aborts, total_txns, percentage, message_calls, percentage_mc)
		stats += (seq_work, para_work, total_work, speedup)
		return format_str % stats

	def save_gantt_stats(self):
		histories = self.evm.get_histories()
		data_file = self.gantt_dir.new_file(str(self.evm.block) + ".csv")

		for proc, hist in enumerate(histories):
			accum = 0
			for n in hist:
				if n == 0:
					continue
				data_file.write("%d,%d,%d\n" % (proc, accum, n))
				accum += n

		data_file.close()

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

	#ret = json.loads(base64.b64decode(res["result"]))
	#return ret
	print "Traced %s" % txn
	return res["result"]
trace_pool = multiprocessing.Pool(16)

# Get transaction hashes and total gas used
def get_transactions(block):
	payload = {"jsonrpc":"2.0", "method":"eth_getBlockByNumber", "params": [hex(block), True], "id": 1}
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()

	#print res
	txns = [txn["hash"] for txn in res["result"]["transactions"]]
	return txns

# Rewritten to use SQLite instead, since all those inserts
# were trashing tstaff's postgres log files
class DBWrapper:
	def __init__(self, db_conn):
		self.db_conn = db_conn

	def block_exists(self, block):
		cursor = self.db_conn.cursor()
		cursor.execute("SELECT block FROM block WHERE block = ?", (block,))
		if not cursor.fetchone():
			ret = False
		else:
			ret = True
		cursor.close()
		return ret

	def get_traces(self, block):
		cursor = self.db_conn.cursor()
		cursor.execute("SELECT hash, trace FROM txn WHERE block = ?", (block,))

		raw_traces = {rec[0]: rec[1] for rec in cursor.fetchall()}
		cursor.close()
		return self.decode_traces(raw_traces)

	def decode_traces(self, raw_traces):
		# base64 decode + (str -> dict)
		decoder = lambda tr: json.loads(base64.b64decode(tr))
		return {txn_hash: decoder(trace) for txn_hash, trace in raw_traces.items()}

	def save_traces(self, block, raw_traces):
		cursor = self.db_conn.cursor()
		cursor.execute("INSERT INTO block VALUES (?)", (block,))

		# Save raw traces
		for txn_hash, raw_trace in raw_traces.items():
			cursor.execute("INSERT INTO txn VALUES (?, ?, ?)", (block, txn_hash, raw_trace))

		# Commit and close cursor
		self.db_conn.commit()
		cursor.close()

# SQLite is slow, use plain text files instead
# Same API as DBWrapper
class FSWrapper:
	def __init__(self, datadir):
		self.datadir = datadir

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
		db_conn = sqlite3.connect(db_name)
		self.db = DBWrapper(db_conn)

	def calculate_traces(self, txns):
		traces_list = trace_pool.map(trace_transaction, txns)
		return {txns[i]: traces_list[i] for i in xrange(len(txns))}

	def execute_block(self, block):
		# Get transactions (and length of critical path of seq exec)
		txns = get_transactions(block)

		# Check whether traces have been computed
		# traces: txn_hash -> dict
		if self.db.block_exists(block):
			traces = self.db.get_traces(block)
		else:
			# Compute traces
			raw_traces = self.calculate_traces(txns)
			# Save raw traces
			self.db.save_traces(block, raw_traces)
			# Decode traces
			traces = self.db.decode_traces(raw_traces)

		# Create Transaction objects
		txn_objects = []
		for txn_hash, trace in traces.items():
			txn_objects.append(Transaction(txn_hash, trace))

		# Create and run EVM
		evm = SimEVM(block, txn_objects)
		evm.run()

		# get stats and print
		stats = EVMStats(evm)
		formatted = stats.stats_formatted()
		stats.save_gantt_stats()

		f = open("output.txt", "a")
		f.write(str(block) + '\t' + formatted + '\n')
		f.close()

	def execute_range(self, start_block, end_block):
		for block in xrange(start_block, end_block, self.freq):
			print block
			self.execute_block(block)

#print trace_transaction("0x90cba76c95b715fbbbc3473f6441a45c5ade78a718de5fd7fde00cf13c254509")
#tr = trace_transaction2("0xe5c0b9656aba44735008202d975dd4f9ca07db5e7b2ec4611d63237fd45974b0")
#for rec in tr["structLogs"]:
#	print rec
#	if rec["op"] == "CALL":
#		print "@o@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
m = Main()
# 4551720
#m.execute_block(4330000)
m.execute_range(4330000, 4380000)
