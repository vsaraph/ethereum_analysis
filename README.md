# Ethereum transaction analyzer

This is roughly the code I used to analyze Ethereum transaction execution, under the hypothetical scenario that the EVM (Ethereum virtual machine) can run transactions concurrently,
using simple software transactions. The work was published at the inaugural Tokenomics conference: [link](https://drops.dagstuhl.de/opus/volltexte/2020/11968/pdf/OASIcs-Tokenomics-2019-4.pdf)

Code quality is research-grade only. Depends on having access to an archive node's JSON RPC API, which can replay and create traces of old transactions on the blockchain, including side effects on contracts' persistent storage.
