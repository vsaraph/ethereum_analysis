# Each processor executes some number of transactions


class Processor:
    # (TODO) use enums (or something similar) to represent
    # process states (FINISHED, NOFUEL, ABORTED)
    # (TODO) add support needed for creating Gantt charts

    # If is_gas is used, units of fuel are measured in gas units,
    # otherwise, measured by instruction count.
    def __init__(self, storage, is_gas=False):
        # 'fuel' is to either gas or instructions available
        self.is_gas = is_gas
        self.storage = storage

        self.pc = 0
        self.fuel = 0
        self.work_done = 0
        self.lifetime_work = 0
        self.txn = None

    # Assign new transaction object
    def new_transaction(self, txn):
        self.txn = txn
        self.pc = 0
        self.fuel = 0

    def step_instruction(self):
        # first check if txn has finished
        if self.pc >= self.txn.instruction_count():
            return "FINISHED"

        # next, check if there is enough gas
        op = self.txn.get_op_at(self.pc)
        cost = self.txn.get_gas_at(self.pc) if self.is_gas else 1
        if cost <= self.fuel:
            self.fuel -= cost
            self.work_done += cost
        else:
            return "NOFUEL"

        # now check for SSTORE/SLOAD
        txn_hash = self.txn.get_hash()
        addr = self.txn.get_addr_at(self.pc)
        if op in ["SSTORE", "SLOAD"]:
            is_write = (op == "SSTORE")
            conflict = self.storage.access(txn_hash, addr, is_write)
            if conflict:
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
    def update_lifetime_work(self):
        self.lifetime_work += self.work_done

    def get_lifetime_work(self):
        return self.lifetime_work
