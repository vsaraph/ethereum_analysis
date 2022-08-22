# This class includes several getters to retrieve information
# about a given transaction. The constructor takes the transaction hash
# and the trace. (TODO) include JSON example of trace here.


class Transaction:
    def __init__(self, txn_hash, trace):
        self.txn_hash = txn_hash
        self.trace = trace
        
    def get_hash(self):
        return self.txn_hash

    def get_op_at(self, pc):
        return self.trace[pc]["op"]

    def get_addr_at(self, pc):
        # (account address, storage addres) pair
        return (self.trace[pc]["account"], self.trace[pc]["location"])

    def get_gas_at(self, pc):
        if pc >= len(trace) - 1:
            return 0
        # difference between one instruction and the next
        return int(self.trace[pc]["gas_left"]) - int(self.trace[pc+1]["gas_left"])

    def total_gas(self):
        if not self.trace:
            return 0
        # difference between first and last instructions
        return self.trace[0]["gas_left"] - self.trace[-1]["gas_left"]

    def instruction_count(self):
        return len(self.trace)

