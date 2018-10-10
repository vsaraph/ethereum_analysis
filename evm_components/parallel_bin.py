# Greedily execute all transactions in parallel

import random
import copy
from storage import Storage
from processor import Processor


class ParallelBin:
    def __init__(self, txns, is_gas, N):
        self.is_gas = is_gas  # running simulation using gas vs # of steps
        self.n_proc = min(N, len(txns))  # use only number of processors needed

        # randomly shuffle given transactions
        self.txns = copy.copy(txns)
        random.shuffle(self.txns)

        # create storage
        self.storage = Storage()

        # create processors
        self.processors = [Processor(self.storage, is_gas) for n in xrange(self.n_proc)]
        self.processor_ids = range(self.n_proc)

        # define stipend
        # fuel allocated for each step
        self.stipend = 100 if is_gas else 5

    # Run one parallel round
    # returns aborted transactions
    def run(self):
        # Assign initial transactions to processors
        for processor in self.processors:
            txn = self.txns.pop(0)
            processor.new_transaction(txn)

        # Aborted transactions
        aborted = []

        # End when there are no more running processors
        while self.processor_ids:
            # Choose a processor
            n = random.choice(self.processor_ids)
            processor = self.processors[n]

            # Run it. If not done, continue with another.
            ret = processor.step(self.stipend)
            if not ret:
                continue

            # Otherwise, update lifetime work
            processor.update_lifetime_work()

            # If it aborted, take note of this
            if ret == "ABORTED":
                aborted.append(processor.txn)

            # If there are transactions remaining, get a new one
            # Otherwise delete this processor, since it is done
            if self.txns:
                new_txn = self.txns.pop(0)
                processor.new_transaction(new_txn)
            else:
                self.processor_ids.remove(n)

        # return aborted txns (to be passed to next round)
        return aborted

    # Maximum over total work of each processor
    def get_maximum_work(self):
        return max([0] + [p.get_lifetime_work() for p in self.processors])