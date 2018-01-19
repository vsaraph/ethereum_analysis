# Vikram Saraph
# get top k weeks that are most active

import requests
import sys

length = 60*60
inc = 60

def get_number_of_txns(block_id):
	payload = {"jsonrpc":"2.0", "method": "eth_getBlockTransactionCountByNumber", "params": [hex(block_id)], "id": 1}
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()

	return int(res["result"], 16)

def get_timestamp(block_id):
	payload = {"jsonrpc": "2.0", "method": "eth_getBlockByNumber", "params": [hex(block_id), False], "id": 1} 
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()

	return int(res["result"]["timestamp"], 16)

def all_timestamps():
	payload = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
	req = requests.post("http://127.0.0.1:8545", json = payload)
	res = req.json()

	start_block = max(4000000, 0)
	end_block = min(4001000, int(res["result"], 16))
	timestamps = []
	txn_count = {}
	block_at_time = {}
	for block_id in xrange(start_block, end_block + 1):
		if block_id % 100 == 0:
			print block_id
		timestamp = get_timestamp(block_id)
		timestamps.append(timestamp)
		txn_count[timestamp] = get_number_of_txns(block_id)
		block_at_time[timestamp] = block_id
	
	return timestamps, txn_count, block_at_time

def find_max_interval(timestamps, txn_count, block_at_time, forbidden = None):

	# initialize
	start_time = timestamps[0]
	end_time = start_time + length
	max_start_idx = 0
	max_end_idx = 0
	max_interval_count = 0
	while max_end_idx < len(timestamps) and timestamps[max_end_idx] < end_time:
		timestamp = timestamps[max_end_idx]
		max_interval_count += txn_count[timestamp]
		max_end_idx += 1

	start_idx = max_start_idx
	end_idx = max_end_idx
	interval_count = max_interval_count

	while end_time < timestamps[-1]:

		# add new txns to count
		while timestamps[end_idx] < end_time:
			timestamp = timestamps[end_idx]
			interval_count += txn_count[timestamp]
			end_idx += 1

		# subtract old txns from count
		while timestamps[start_idx] < start_time:
			timestamp = timestamps[start_idx]
			interval_count -= txn_count[timestamp]
			start_idx += 1

		# compare interval_count to max
		# if new max, save data
		if interval_count > max_interval_count:
			max_interval_count = interval_count
			max_start_idx = start_idx
			max_end_idx = end_idx

		# move start_time and end_time forward
		start_time += inc
		end_time += inc
	
	max_end_idx = min(max_end_idx, len(timestamps)-1)

def find_k_max_intervals():
	timestamps, txn_count, block_at_time = all_timestamps()



find_max_interval(timestamps, txn_count, block_at_time)
