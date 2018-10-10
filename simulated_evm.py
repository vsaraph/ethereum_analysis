from evm_components.parallel_bin import ParallelBin
from evm_components.transaction import Transaction
from database import Database
import os
import yaml

config = yaml.safe_load(open("config.yml"))


class SimulatedEVM:
    def __init__(self, block, bins, n_proc, is_gas=False):
        self.is_gas = is_gas	    # run simulation using gas or # inst

        # Fetch transactions from database
        db = Database()
        self.txns = [Transaction(txn_hash, trace) for txn_hash, trace in db.load_block(block).items()]

        self.n_proc = n_proc	    # number of processors per bin
        self.bins = bins		    # number of bins
        self.bin_work = []		    # work per bin
        self.aborted = []		    # aborted

        # calculate cost of each transaction
        self.txn_fuel = {}
        for txn in self.txns:
            txn_hash = txn.txn_hash
            if is_gas:
                self.txn_fuel[txn_hash] = txn.total_gas()
            else:
                self.txn_fuel[txn_hash] = txn.instruction_count()

    # Run several rounds of ParallelBins
    def run(self):
        aborted = self.txns
        for b in xrange(self.bins):
            # run one parallel bin
            parallel_bin = ParallelBin(aborted, self.is_gas, self.n_proc)
            aborted = parallel_bin.run()

            # get (parallel) work of bin
            self.bin_work.append(parallel_bin.get_maximum_work())

        self.aborted = aborted

    # total by parallel bins
    def parallel_phase_work(self):
        return sum(self.bin_work)

    # Work by sequential transactions
    def sequential_phase_work(self):
        return sum([self.txn_fuel[txn.txn_hash] for txn in self.aborted])

    # Work done by a regular EVM
    def sequential_evm_work(self):
        return sum(self.txn_fuel.values())

    # Number of message calls
    def get_message_calls(self):
        message_calls = 0
        for txn in self.txns:
            if txn.trace:
                message_calls += 1
        return message_calls

    # Append statistics to a given file
    def write_statistics(self, filename):
        # percentage aborts
        aborts = len(self.aborted)
        total_txns = len(self.txn_fuel)
        message_calls = self.get_message_calls()

        if total_txns != 0:
            percentage_tx = float(aborts) / total_txns
        else:
            percentage_tx = float('nan')

        if message_calls != 0:
            percentage_mc = float(aborts) / message_calls
        else:
            percentage_mc = float('nan')

        # critical path calculation
        sequential_phase_work = self.sequential_phase_work()
        parallel_phase_work = self.parallel_phase_work()
        sequential_evm_work = self.sequential_evm_work()
        parallel_evm_work = sequential_phase_work + parallel_phase_work

        if parallel_evm_work != 0:
            speedup = float(sequential_evm_work) / parallel_evm_work
        else:
            speedup = float('nan')

        # return formatted str
        format_str = "%d\t%d\t%0.2f\t%d\t%0.2f\t%d\t%d\t%d\t%0.2f\n"
        stats = (aborts, total_txns, percentage_tx, message_calls, percentage_mc)
        stats += (sequential_phase_work, parallel_phase_work, sequential_evm_work, speedup)

        open(filename, 'a').write(format_str % stats)

if __name__ == "__main__":
    for b in xrange(525700, 525710):
        evm = SimulatedEVM(b, 1, 4)
        evm.run()
        evm.write_statistics("test.txt")