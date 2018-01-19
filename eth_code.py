# Vikram Saraph
# first pass at writing functions to analyze the Ethereum blockchain

import requests
import json
import time
import multiprocessing
import sys
import base64

etherchain_last = 0

# javascript code
rw_tracer = """{data: [],
	step: function(log) {
		opstr = log.op.toString();
		if (opstr == "SSTORE" || opstr == "SLOAD")
			this.data.push([opstr, log.account, log.stack.peek(0)]);
	},
	result: function() {return this.data; }
	}"""

rw_bal_call_tracer = """{data: [],
	step: function(log) {
		opstr = log.op.toString();
		if (opstr == "SSTORE" || opstr == "SLOAD")
			this.data.push([opstr, log.account, log.stack.peek(0)]);
		else if (opstr == "BALANCE")
			this.data.push([opstr, log.stack.peek(0)]);
		else if (opstr == "CALL")
			this.data.push([opstr, log.account]);
	},
	result: function() {return this.data; }
	}"""

event_tracer = """{data: [],
	step: function(log) {
		op = log.op.toString();
		data_delta = {}
		data_delta["op"] = op;
		data_delta["depth"] = log.depth;
		if (op == "SSTORE") {
			data_delta["loc"] = log.stack.peek(0);
			data_delta["val"] = log.stack.peek(1);
		}
		else if (op == "SLOAD")
			data_delta["loc"] = log.stack.peek(0);
		else if (op == "RETURN") {}
		else if (op == "CALL") {
			offset = Number(log.stack.peek(3).String());
			size = Number(log.stack.peek(4).String());
			data_delta["addr"] = log.stack.peek(1);
			data_delta["input"] = log.memory.slice(offset, offset + size);
		}
		else {return;}
		this.data.push(data_delta);
	},
	result: function() {return this.data; }
	}"""

def get_sender(txn):
	payload = {"jsonrpc":"2.0", "method":"eth_getTransactionByHash", "params": [txn], "id":1}
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()

	return res["result"]["from"]

def get_events(txn):
	raw_events = trace_transaction(txn, event_tracer)

	# get top-level sender
	sender = get_sender(txn)

	# process each event to comply with API
	events = []
	for raw_event in raw_events:
		event = {}
		op = raw_event["op"]
		event["depth"] = raw_event["depth"]
		data = {}
		event["type"] = {"sender": sender, "op": op, "data": data}
		if op == "CALL":
			data["addr"] = hex(raw_event["addr"]).rstrip("L")
			input_data = raw_event["input"]
			if input_data:
				data["input"] = "0x" + base64.b64decode(raw_event["input"]).encode('hex')
			else:
				data["input"] = None
		elif op == "SLOAD":
			data["loc"] = raw_event["loc"]
		elif op == "SSTORE":
			data["loc"] = raw_event["loc"]
			data["val"] = raw_event["val"]
		events.append(event)
	return events

# trace one transaction using the JS tracer
def trace_transaction(txn):
	payload = {"jsonrpc":"2.0", "method":"debug_traceTransaction", "params":[txn, {"tracer": rw_bal_call_tracer, "timeout": "1h"}], "id": 1}
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()	

	return res["result"]

trace_pool = multiprocessing.Pool(12)
# take a set of potentially conflicting transaction
# use debug_traceTransaction to calculate
def get_deep_conflicts(txns):
	txns = list(txns)
	accesses_all = trace_pool.map(lambda t: trace_transaction(t, rw_tracer), txns)
	accesses_dict = {txns[i]: accesses_all[i] for i in xrange(len(txns))}

	accessed_by = {} # (contract, storage) -> set(txn_hash)
	has_write = set() # contains (contract, storage) with write
	conflicting_txns = set()

	# first get access pattern
	for txn in txns:
		accesses = accesses_dict[txn]
		for op, cont_addr, store_addr in accesses:
			if op == "SSTORE":
				has_write.add((cont_addr, store_addr))
			if (cont_addr, store_addr) not in accessed_by:
				accessed_by[(cont_addr, store_addr)] = set([txn])
			else:
				other_txns = accessed_by[(cont_addr, store_addr)]
				other_txns.add(txn)
	
	# then count conflicts
	for addr in has_write:
		if len(accessed_by[addr]) > 1:
			conflicting_txns.update(accessed_by[addr])
	
	return conflicting_txns

trace_pool2 = multiprocessing.Pool(12)
bal_tracer = lambda t: trace_transaction(t, rw_bal_call_trace)
# Similar to 
# Include BALANCE / CALL conflicts
# senders: txn -> sender
def get_bal_conflicts(txns, senders):
	txns = list(txns)		# cast to list, needed to use thread pool
	events_all = trace_pool2.map(trace_transaction, txns)
	events_dict = {txns[i]: events_all[i] for i in xrange(len(txns))}

	accessed_by = {}		# (contract, storage) -> set(txn_hash)
	has_write = set()		# contains (contract, storage) with at least one write
	acct_accessed_by = {}	# account -> set(txn_hash)
	acct_has_send = set()	# contains account with at least one send
	acct_has_bal = set()

	conflicting_rw_txns = set() # only caused by SSTORE / SLOAD conflict
	conflicting_txns = set()	# also includes BALANCE / CALL conflict

	# first get access pattern
	for txn in txns:
		# add sender
		acct = senders[txn]
		if acct not in acct_accessed_by:
			acct_accessed_by[acct] = set([txn])
		else:
			acct_accessed_by[acct].add(txn)

		events = events_dict[txn]
		for event in events:
			op = event[0]
			if op in ["SSTORE", "SLOAD"]:
				cont_addr, store_addr = event[1:]
				if op == "SSTORE":
					has_write.add((cont_addr, store_addr))
				if (cont_addr, store_addr) not in accessed_by:
					accessed_by[(cont_addr, store_addr)] = set([txn])
				else:
					other_txns = accessed_by[(cont_addr, store_addr)]
					other_txns.add(txn)
			elif op in ["CALL", "BALANCE"]:
				acct = event[1]
				if op == "CALL":
					acct_has_send.add(acct)
				else:
					acct_has_bal.add(acct)
				if acct not in acct_accessed_by:
					acct_accessed_by[acct] = set([txn])
				else:
					other_txns = acct_accessed_by[acct]
					other_txns.add(txn)

	# then count rw conflicts
	for addr in has_write:
		if len(accessed_by[addr]) > 1:
			conflicting_rw_txns.update(accessed_by[addr])

	# and add bal/call conflicts
	conflicting_txns.update(conflicting_rw_txns)
	for acct in acct_has_send:
		if acct not in acct_has_bal:
			continue
		if len(acct_accessed_by[acct]) > 1:
			conflicting_txns.update(acct_accessed_by[acct])

	return conflicting_rw_txns, conflicting_txns

def is_contract(address):
	payload = {"jsonrpc":"2.0", "method":"eth_getCode", "params": [address, "latest"], "id": 1}
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()

	return (res["result"] != "0x")

# return list of tuples
def get_eth_camp(block_id, deep=False):

	# get number of txns and block hash
	block_method = "https://temp.ether.camp/api/v1/search/blocks/by-number"
	block_res = requests.get(block_method, params = {"number": block_id}, verify=False)
	if not block_res.ok:
		return (False, None, None, None, None)
	block_data = block_res.json()
	if "content" not in block_data or not block_data["content"]:
		return (False, None, None, None, None)
	block_hash = block_data["content"][0]["hash"]
	txns_count = block_data["content"][0]["transactionCount"]

	# get transactions
	txns_method = "https://temp.ether.camp/api/v1/blocks/%s/transactions"
	try:
		txns_res = requests.get(txns_method % block_hash, params = {"page": 0, "size": max(1, txns_count), "direction": "ASC"}, verify=False, timeout = 6)
	except requests.exceptions.Timeout:
		print "ETHER CAMP TIMEOUT"
		return (False, None, None, None, None)
	if not txns_res.ok:
		return (False, None, None, None, None)
	txns_data = txns_res.json()
	
	called_by = {} # address -> set of txn
	top_hash = get_root_hashes(txns_data["content"])
	unique_txns = set()
	txn_count = 0

	# get address map
	for txn_data in txns_data["content"]:
		# ignore value transfers
		txn_type = txn_data["type"]
		if not txn_type.startswith("INTER"):
			txn_count += 1
		if txn_type == "VALUE":
			continue

		# get txn hash
		txn_hash = top_hash[txn_data["hash"]]
		unique_txns.add(txn_hash)

		# save called addresses
		address = txn_data["toAddress"]
		if address not in called_by:
			called_by[address] = set([txn_hash])
		else:
			other_txns = called_by[address]
			other_txns.add(txn_hash)

	# calculate conflicts
	conflicting_txns = set()
	for address in called_by:
		txns = called_by[address]
		if len(txns) > 1:
			conflicting_txns.update(["0x" + txn for txn in txns])
	
	# get deep conflicts, only of conflicting_txns
	deep_count = None
	if deep:
		deep_conflicting = get_deep_conflicts(conflicting_txns)
		deep_count = len(deep_conflicting)

	return (True, txn_count, len(unique_txns), len(conflicting_txns), deep_count)

# get top-level hashes
def get_root_hashes(txns_data):
	top_hash = {}
	for txn_data in txns_data:
		txn_hash = txn_data["hash"]
		# top-level already
		if "internalTransactionsCount" in txn_data:
			top_hash[txn_hash] = txn_hash
		else:
			parent_index = int(txn_data["globalIndex"].split(".")[1])
			top_hash[txn_hash] = txns_data[parent_index]["hash"]
	return top_hash

# use etherchain
def get_eth_chain(block_id, deep=False):
	global etherchain_last
	txns_method = "https://etherchain.org/api/block/%s/tx"

	while int(time.time()) - etherchain_last <= 6:
		print "ETHERCHAIN WAITING"
		time.sleep(1)

	txns_res = requests.get(txns_method % block_id)
	if not txns_res.ok:
		return (False, None, None, None, None)
	etherchain_last = int(time.time())
	txns_data = txns_res.json()

	called_by = {}
	unique_txns = set()
	txn_count = 0
	for txn_data in txns_data["data"]:
		txn_type = txn_data["type"]
		address = txn_data["recipient"]
		# ignore value transfers
		if txn_type == "tx" :
			txn_count += 1
			if not is_contract(address):
				continue

		# get hash
		txn_hash = txn_data["parentHash"]
		unique_txns.add(txn_hash)

		# save called addresses
		if address not in called_by:
			called_by[address] = set([txn_hash])
		else:
			other_txns = called_by[address]
			other_txns.add(txn_hash)

	# calculate conflicts
	conflicting_txns = set()
	for address in called_by:
		txns = called_by[address]
		if len(txns) > 1:
			conflicting_txns.update(txns)

	# get deep conflicts, only of conflicting_txns
	deep_count = None
	if deep:
		deep_conflicting = get_deep_conflicts(conflicting_txns)
		deep_count = len(deep_conflicting)

	return (True, txn_count, len(unique_txns), len(conflicting_txns), deep_count)

# use geth
def get_geth(block_id):
	# get txns and senders from given block
	payload = {"jsonrpc":"2.0", "method":"eth_getBlockByNumber", "params": [hex(block_id), True], "id": 1}
	req = requests.post("http://127.0.0.1:8545", json = payload, verify="False")
	res = req.json()

	txns = [txn["hash"] for txn in res["result"]["transactions"]]
	senders = {txn["hash"]: txn["from"] for txn in res["result"]["transactions"]}

	# pass to get_bal_conflicts
	rw_txns, all_txns = get_bal_conflicts(txns, senders)

	return (len(rw_txns), len(all_txns), len(txns))

# run through blocks
def block_range_bal(start_block, end_block, rate=10):
	conf_file = open("BAL_%d_%d" % (start_block, end_block), 'w')
	conf_file.close()
	for block_id in xrange(start_block, end_block+1, rate):
		x, y, z = get_geth(block_id)

		conf_file = open("BAL_%d_%d" % (start_block, end_block), 'a')
		conf_file.write("%d\t%d\t%d\t%d\n" % (block_id, x, y, z))
		conf_file.close()
		print block_id

def find_txn_without_call(start_block):
	block = start_block
	while True:
		payload = {"jsonrpc":"2.0", "method":"eth_getBlockByNumber", "params": [hex(block), True], "id": 1}
		req = requests.post("http://127.0.0.1:8545", json = payload, verify="False")
		res = req.json()

		txns = [txn["hash"] for txn in res["result"]["transactions"]]

		disable = {"disableStack": True, "disableMemory": True, "disableStorage": True}

		for txn in txns:
			payload = {"jsonrpc":"2.0", "method":"debug_traceTransaction", "params":[txn, disable], "id": 1}
			req = requests.post("http://127.0.0.1:8545", json = payload, verify="False")
			res = req.json()

			ops = [step["op"] for step in res["result"]["structLogs"]]
			if ops and "CALL" in ops:
				count = 0
				for op in ops:
					if op == "CALL":
						count += 1
				return block, txn, count

		block += 1

# block range stats for pessimistic conflict calculation
# two transactions conflict if they access same contract
def block_range_stats(start_block, end_block, deep=False):
	conf_file = open("CONFLICTS_%d_%d" % (start_block, end_block), 'w')
	conf_file.close()
	for block_id in xrange(start_block, end_block+1):
		# if one doesn't work, try the other
		res, all_txns, uniq, conf, deep_count = get_eth_camp(block_id, deep)
		explorer = "ETHER.CAMP"
		if not res:
			explorer = "ETHERCHAIN"
			_, all_txns, uniq, conf, deep_count = get_eth_chain(block_id, deep)
		if uniq == None:
			with open("LOG_FILE", 'a') as lf:
				lf.write("%d\n" % block_id)
			sys.exit(1)

		if deep:
			print block_id

		conf_file = open("CONFLICTS_%d_%d" % (start_block, end_block), 'a')
		conf_file.write("%s\t%d\t%d\t%d\t%d\t%s\n" % (explorer, block_id, all_txns, uniq, conf, deep_count))
		conf_file.close()

#print trace_transaction("0x72208b10823d0940276c225e5d08bf6e8b02265489c5acf09f0da73dfacebe25", event_tracer)
#print json.dumps(get_events("0x11b54a91f7b8319c1cfa1662760c27e092a3d35d8a63e1d713bd7a1670cd72d4"), indent=4, sort_keys=True)

block_range_bal(4230000, 4260000)
#block_range_stats(4230001, 4260000, True)


#block_range_bal(4230001, 4260000)
