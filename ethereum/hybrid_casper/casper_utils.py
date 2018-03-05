import os
import sys
import copy

from ethereum import utils, abi, genesis_helpers, config
from ethereum.hybrid_casper.casper_initiating_transactions import mk_initializers, purity_checker_address, purity_checker_abi
from ethereum.hybrid_casper import consensus
from ethereum.hybrid_casper.config import config
from ethereum.messages import apply_transaction
from ethereum.tools import tester
from viper import compiler, optimizer, compile_lll
from viper.parser.parser_utils import LLLnode
import rlp
from ethereum.utils import encode_hex


ethereum_path = os.path.dirname(sys.modules['ethereum'].__file__)
casper_contract_path = '/'.join((ethereum_path, '..', 'casper', 'casper', 'contracts', 'simple_casper.v.py'))
casper_code = open(casper_contract_path).read()
casper_bytecode = compiler.compile(casper_code)
casper_abi = compiler.mk_full_signature(casper_code)
casper_translator = abi.ContractTranslator(casper_abi)
purity_translator = abi.ContractTranslator(purity_checker_abi)



# Get a genesis state which is primed for Casper
def make_casper_genesis(alloc, epoch_length, withdrawal_delay, base_interest_factor, base_penalty_factor, genesis_declaration=None, db=None):
    # The Casper-specific dynamic config declaration
    config.casper_config['EPOCH_LENGTH'] = epoch_length
    config.casper_config['WITHDRAWAL_DELAY'] = withdrawal_delay
    config.casper_config['OWNER'] = tester.a0
    config.casper_config['BASE_INTEREST_FACTOR'] = base_interest_factor
    config.casper_config['BASE_PENALTY_FACTOR'] = base_penalty_factor
    # Get initialization txs
    init_txs, casper_address = mk_initializers(config.casper_config, config.casper_config['SENDER'])
    config.casper_config['CASPER_ADDRESS'] = casper_address
    # Create state and apply required state_transitions for initializing Casper
    if genesis_declaration is None:
        state = genesis_helpers.mk_basic_state(alloc, None, env=config.Env(config=config.casper_config, db=db))
    else:
        state = genesis_helpers.state_from_genesis_declaration(genesis_declaration, config.Env(config=config.casper_config, db=db))
    state.gas_limit = 10**8
    for tx in init_txs:
        state.set_balance(utils.privtoaddr(config.casper_config['SENDER']), 15**18)
        success, output = apply_transaction(state, tx)
        assert success
        state.gas_used = 0
        state.set_balance(utils.privtoaddr(config.casper_config['SENDER']), 0)
        state.set_balance(casper_address, 10**25)
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


def validators(casper):
    validator_indexes = casper.get_nextValidatorIndex()
    validators = []
    for i in range(validator_indexes + 1):
        validator_index = i+1
        v = {}
        v["addr"] = casper.get_validators__addr(validator_index)
        v["start_dynasty"] = casper.get_validators__start_dynasty(validator_index)
        v["end_dynasty"] = casper.get_validators__end_dynasty(validator_index)
        v["deposit"] = casper.get_deposit_size(validator_index)
        validators.append(v)
    return validators

def votes_and_deposits(casper, ce, ese):
    cur_deposits = casper.get_total_curdyn_deposits()
    prev_deposits = casper.get_total_prevdyn_deposits()

    cur_votes = 0 #change: current_votes is always 0
    prev_votes = casper.get_votes__prev_dyn_votes(ce, ese) * casper.get_deposit_scale_factor(ce)
    cur_vote_pct = cur_votes * 100 / cur_deposits if cur_deposits else 0
    prev_vote_pct = prev_votes * 100 / prev_deposits if prev_deposits else 0
    last_nonvoter_rescale, last_voter_rescale = casper.get_last_nonvoter_rescale(), casper.get_last_voter_rescale()
    return {
        "cur_deposits":cur_deposits,
        "prev_deposits":prev_deposits,
        "cur_votes":cur_votes,
        "prev_votes":prev_votes,
        "cur_vote_pct":cur_vote_pct,
        "prev_vote_pct":prev_vote_pct,
        "last_nonvoter_rescale":last_nonvoter_rescale,
        "last_voter_rescale":last_voter_rescale
    }


def epoch_info(epoch,eth):
    epoch_length = eth.chain.config['EPOCH_LENGTH']
    height = epoch * epoch_length + (epoch_length - 1) #change: capture data at end of epoch
    blockhash = eth.chain.get_blockhash_by_number(height)

    temp_state = eth.chain.mk_poststate_of_blockhash(blockhash)
    casper = tester.ABIContract(tester.State(temp_state), casper_abi, eth.chain.config['CASPER_ADDRESS'])
    

    ce, ese = casper.get_current_epoch(), casper.get_expected_source_epoch()
    
    info = {}
    info["number"] = height
    info["blockhash"] = encode_hex(blockhash)
    info["current_epoch"] = ce
    info["validators"] = validators(casper)
    info["lje"] = casper.get_last_justified_epoch()
    info["lfe"] = casper.get_last_finalized_epoch()
    info["votes"] = votes_and_deposits(casper, ce, ese)
    return info
