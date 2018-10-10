# Detect conflicts
# Keep a hash table of accessed storage locations


class Storage:
    def __init__(self, exclusive = False):
        self.map = {}
        self.has_write = set()
        self.exclusive = exclusive

    def reset(self):
        self.map = {}
        self.has_write = set()

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
                return True

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
        return True