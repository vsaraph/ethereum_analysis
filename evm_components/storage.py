# Detect conflicts
# Keep a hash table of accessed storage locations


class Storage:
    def __init__(self, exclusive=False):
        self.map = {}
        self.has_write = set()
        self.exclusive = exclusive
        self.conflicts = {}

    def reset(self):
        self.map = {}
        self.has_write = set()

    def conflict_at(self, addr):
        if addr in self.conflicts:
            self.conflicts[addr] += 1
        else:
            self.conflicts[addr] = 1
        return True

    def access(self, txn_hash, addr, is_write):
        # exclusive
        if self.exclusive:
            if addr not in self.map:
                self.map = txn_hash
                # no conflict
                return False
            elif self.map[addr] == txn_hash:
                # no conflict
                return False
            else:
                # conflict
                return self.conflict_at(addr)

        # non-exclusive
        if addr not in self.map:
            # fresh address
            self.map[addr] = txn_hash
            if is_write:
                self.has_write.add(addr)
            return False    # no conflict
        if self.map[addr] == txn_hash:
            # you are the sole reader/writer
            if is_write:
               self.has_write.add(addr)
            return False
        self.map[addr] = None
        if not is_write and addr not in self.has_write:
            # another read - no conflict
            return False
        return self.conflict_at(addr)

    def hotspot_count(self, threshold):
        return len([addr for addr, count in self.conflicts.items() if count >= threshold])
