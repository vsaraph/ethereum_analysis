from sys import argv

# take list of files and aggregate all of them

files = argv[1:]
txns = 0
c_txns = 0
p_conf = 0
conf = 0
count = 0
for f_name in files:
	f = open(f_name)
	for line in f:
		count += 5
		if count % 10 != 0:
			continue
		_, _, txns_d, c_txns_d, p_conf_d, conf_d = line.strip().split()
		txns += int(txns_d)
		c_txns += int(c_txns_d)
		p_conf += int(p_conf_d)
		conf += int(conf_d)

print float(conf) / txns
print float(conf) / c_txns
print float(p_conf) / txns
print float(p_conf) / c_txns
