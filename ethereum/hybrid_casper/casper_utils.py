import os
import sys
import copy

from ethereum import utils, abi, genesis_helpers, config
from ethereum.hybrid_casper.casper_initiating_transactions import mk_initializers, purity_checker_address, purity_checker_abi
from ethereum.hybrid_casper import consensus
from ethereum.messages import apply_transaction
from ethereum.tools.tester import a0
from viper import compiler, optimizer, compile_lll
from viper.parser.parser_utils import LLLnode
import rlp

ethereum_path = os.path.dirname(sys.modules['ethereum'].__file__)
casper_contract_path = '/'.join((ethereum_path, '..', 'casper', 'casper', 'contracts', 'simple_casper.v.py'))
casper_code = open(casper_contract_path).read()
casper_bytecode = compiler.compile(casper_code)
casper_abi = compiler.mk_full_signature(casper_code)
casper_translator = abi.ContractTranslator(casper_abi)
purity_translator = abi.ContractTranslator(purity_checker_abi)

# Get a genesis state which is primed for Casper
def make_casper_genesis(alloc, epoch_length, withdrawal_delay, base_interest_factor, base_penalty_factor):
    # The Casper-specific config declaration
    casper_config = copy.deepcopy(config.default_config)
    casper_config['HOMESTEAD_FORK_BLKNUM'] = 0
    casper_config['ANTI_DOS_FORK_BLKNUM'] = 0
    casper_config['CLEARING_FORK_BLKNUM'] = 0
    casper_config['CONSENSUS_STRATEGY'] = 'hybrid_casper'
    casper_config['NULL_SENDER'] = utils.sha3('NULL_SENDER')
    casper_config['EPOCH_LENGTH'] = epoch_length
    casper_config['WITHDRAWAL_DELAY'] = withdrawal_delay
    casper_config['OWNER'] = a0
    casper_config['BASE_INTEREST_FACTOR'] = base_interest_factor
    casper_config['BASE_PENALTY_FACTOR'] = base_penalty_factor
    # Get initialization txs
    init_txs, casper_address = mk_initializers(casper_config, casper_config['NULL_SENDER'])
    casper_config['CASPER_ADDRESS'] = casper_address
    # Create state and apply required state_transitions for initializing Casper
    state = genesis_helpers.mk_basic_state(alloc, None, env=config.Env(config=casper_config))
    state.gas_limit = 10**8
    for tx in init_txs:
        state.set_balance(utils.privtoaddr(casper_config['NULL_SENDER']), 15**18)
        success, output = apply_transaction(state, tx)
        assert success
        state.gas_used = 0
        state.set_balance(utils.privtoaddr(casper_config['NULL_SENDER']), 0)
    consensus.initialize(state)
    state.commit()
    return state


def mk_validation_code(address):
    validation_code_maker_lll = LLLnode.from_list(['seq',
                                ['return', [0],
                                    ['lll',
                                        ['seq',
                                            ['calldatacopy', 0, 0, 128],
                                            ['call', 3000, 1, 0, 0, 128, 0, 32],
                                            ['mstore', 0, ['eq', ['mload', 0], utils.bytes_to_int(address)]],
                                            ['return', 0, 32]
                                        ],
                                    [0]]
                                ]
                            ])
    validation_code_maker_lll = optimizer.optimize(validation_code_maker_lll)
    return compile_lll.assembly_to_evm(compile_lll.compile_to_assembly(validation_code_maker_lll))


# Helper functions for making a prepare, commit, login and logout message

def mk_vote(validator_index, target_hash, target_epoch, source_epoch, key):
    sighash = utils.sha3(rlp.encode([validator_index, target_hash, target_epoch, source_epoch]))
    v, r, s = utils.ecdsa_raw_sign(sighash, key)
    sig = utils.encode_int32(v) + utils.encode_int32(r) + utils.encode_int32(s)
    return rlp.encode([validator_index, target_hash, target_epoch, source_epoch, sig])

def mk_logout(validator_index, epoch, key):
    sighash = utils.sha3(rlp.encode([validator_index, epoch]))
    v, r, s = utils.ecdsa_raw_sign(sighash, key)
    sig = utils.encode_int32(v) + utils.encode_int32(r) + utils.encode_int32(s)
    return rlp.encode([validator_index, epoch, sig])

def induct_validator(chain, casper, key, value):
    sender = utils.privtoaddr(key)
    valcode_addr = chain.tx(key, "", 0, mk_validation_code(sender))
    assert utils.big_endian_to_int(chain.tx(key, purity_checker_address, 0, purity_translator.encode('submit', [valcode_addr]))) == 1
    casper.deposit(valcode_addr, sender, value=value)
