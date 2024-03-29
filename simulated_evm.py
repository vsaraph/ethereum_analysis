from evm_components.parallel_bin import ParallelBin
from evm_components.transaction import Transaction
from database import Database
import os
import yaml

config = yaml.safe_load(open("config.yml"))


class SimulatedEVM:
    def __init__(self, block, bins, n_proc, is_gas=False):
        self.block = block
        self.is_gas = is_gas	    # run simulation using gas or # inst

        # Fetch transactions from database
        db = Database()
        self.txns = [Transaction(txn_hash, trace) for txn_hash, trace in db.load_block(block).items()]

        self.n_proc = n_proc	    # number of processors per bin
        self.bins = bins		    # number of bins
        self.bin_work = []		    # work per bin
        self.aborted = []		    # aborted

        # calculate cost of each transaction
        self.txn_cost = {}
        for txn in self.txns:
            txn_hash = txn.txn_hash
            if is_gas:
                self.txn_cost[txn_hash] = txn.total_gas()
            else:
                self.txn_cost[txn_hash] = txn.instruction_count()

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
        return sum([self.txn_cost[txn.txn_hash] for txn in self.aborted])

    # Work done by a regular EVM
    def sequential_evm_work(self):
        return sum(self.txn_cost.values())

    # Number of message calls
    def get_message_calls(self):
        message_calls = 0
        for txn in self.txns:
            if txn.trace:
                message_calls += 1
        return message_calls

    def unique_contract_ratio(self):
        unique = set()
        for txn in self.txns:
            if txn.trace:
                unique.add(txn.trace[0]["account"])
        mc = self.get_message_calls()
        if (mc > 0):
		    return float(len(unique)) / self.get_message_calls()
        else:
            return float('nan')

    def perfect_speedup(self):
        costs = sorted(self.txn_cost.values(), reverse=True)
        work_per_processor = self.n_proc * [0]
        for cost in costs:
            argmin = min([(w, i) for i, w in enumerate(work_per_processor)])[1]
            work_per_processor[argmin] += cost

        longest = max(work_per_processor)
        if longest > 0:
            return float(sum(costs)) / longest
        else:
            return float('nan')

    # Append statistics to a given file
    def write_statistics(self, filename):
        # percentage aborts
        aborts = len(self.aborted)
        total_txns = len(self.txn_cost)
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
        format_str = "%d\t%d\t%d\t%0.2f\t%d\t%0.2f\t%d\t%d\t%d\t%0.2f\t%0.2f\n"
        stats = (self.block, aborts, total_txns, percentage_tx, message_calls, percentage_mc)
        stats += (sequential_phase_work, parallel_phase_work, sequential_evm_work, speedup)
        stats += (self.perfect_speedup(),)
        print(self.unique_contract_ratio())

        open(filename, 'a').write(format_str % stats)


if __name__ == "__main__":
    open("d8e8fca2dc0f896fd7cb4cb0031ba249.txt", 'w').close()
    start = 3566000
	#start = 4688000 
    end = start + 1000
    for b in xrange(start, end, 10):
        evm = SimulatedEVM(b, 1, 16)
        evm.run()
        evm.write_statistics("d8e8fca2dc0f896fd7cb4cb0031ba249.txt")
