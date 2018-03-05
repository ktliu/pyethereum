[![Build Status](https://travis-ci.org/ethereum/pyethereum.svg?branch=develop)](https://travis-ci.org/ethereum/pyethereum)

 

## Important files for visualization

* Pyethereum.ethereum.test_viz - file for using the visualization + testing lang
* Pyethereum.ethereum.visualization - implements the visualization for casper (following as closely as possible to sharding visualization (thanks kevin))
* Pyethereum.ethereum.tools.tester - where record class is used to gather imformation about the chain
* Pyethereum.ethereum.hybrid_casper.casper_utils - casper smart contract helper for justification/finalization (thanks Chih-Cheng)

Future Todos:

- Add slashing visualization
- Add third edge for votes (any child checkpoint the votes get included in)


Epoch 

![alt text](https://github.com/ktliu/pyethereum/blob/visulization/ethereum/epoch_1.pdf)

Blocks 

![alt text](https://github.com/ktliu/pyethereum/blob/visulization/ethereum/block_1.pdf)

 
