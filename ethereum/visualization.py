from collections import defaultdict
from ethereum.utils import encode_hex #TODO: Remove
import graphviz as gv
EPOCH_LENGTH = 5  #TODO: change hardcoded epoch length 
LEN_HASH = 8


def get_shorten_hash(hash_bytes32):
	return hash_bytes32.hex()[:LEN_HASH]

# Keeps a record of all blocks / votes to be drawn later
class Record(object):

	def __init__(self):

		self.blocks = {} # grabs block header given block hash i.e. {block hash:block header}
		self.mainchain_head_header = None # keep track of mainchain's head  
		self.mainchain_genesis_header = None
		self.blocks_by_height = defaultdict(list) # {block number : [block header]} for drawing mainchain_fork v.2
		self.tx_hashes_in_node = {} 
		self.node_events = defaultdict(list) #mostly for sharding, keep track of events
		self.votes = defaultdict(list) # stores decoded vote message {target hash: vote }
		self.blocks_by_forks = []  # {} for drawing mainchain_fork v.1
		self.justified_blocks = []
	
	def add_block(self, block):
		header = block.header
		self.blocks[header.hash] = header

		#TODO: does casper visualization need tx_hashes?
		tx_hashes = [tx.hash for tx in block.transactions]
		self.tx_hashes_in_node[header.hash] = tx_hashes

		if header.number == 0:
			self.mainchain_genesis_header = header
			print('!@# genesis={}'.format(header.hash))
		if self.mainchain_head_header is None or self.mainchain_head_header.number < header.number:
			self.mainchain_head_header = header

		#for version 2 of mainchain - store blocks by block height to draw forks 
		self.blocks_by_height[header.number].append(block)

		#for version1 of mainchain
		if block.header.number == 0:
			self.blocks_by_forks.append({'start': block, 'end': block})
		else:
			for fork in self.blocks_by_forks:			 
				fork_index = self.blocks_by_forks.index(fork)
				if header.prevhash == fork["end"].header.hash:
					fork['end'] = block #replace head of fork
					self.blocks_by_forks[fork_index] = fork
				elif fork_index == len(self.blocks_by_forks) - 1: #if finished looking through existing forks, create a new fork
					self.blocks_by_forks.append({'start': block, 'end': block}) 
					break

		 
	def add_vote(self, vote):
		validator_index = vote[0]
		_h = vote[1]
		_t = vote[2]
		_s = vote[3]
		
		vote = {'index': validator_index, 'hash': _h, 'target': _t, 'source': _s}
		self.votes[_h].append(vote)

 	# def updated_block_to_justified(self, blocks):
 		#target block, source block
 		#justfied_bocks = {1,2,3,4,5}

	def get_tx_labels_from_node(self, node_hash):
		if node_hash not in self.node_events:
			return []
		return self.node_events[node_hash]

class CasperVisualization(object):

	def __init__(self, filename, tester_chain, draw_in_epoch):
		self.record = tester_chain.record
		self.mainchain = tester_chain.chain


		self.layers = defaultdict(list) #layers is used to store the nodes needed to be drawn at the same height
		self.draw_in_epoch = draw_in_epoch #option to draw at each epoch / block
		self.mainchain_caption = "mainchain" if not draw_in_epoch else "epoch"
		self.vote_caption = "vote"
		self.g = gv.Digraph('G', filename=filename)

	
	
	def draw_block(self, current_hash, prev_hash, label_edges, height):
		prev_node_name = self.get_node_name_from_hash(prev_hash)
		node_name = self.get_node_name_from_hash(current_hash)
		if self.draw_in_epoch:
			caption = '{}'.format(height)
		else:
			caption = 'B{}: {}'.format(height, node_name)
		self.draw_struct(node_name, prev_node_name, height, label_edges, 'record', caption)


	#The function to draw mainchain with forks using draw_chain
	#Cons: need to know parent of fork to stop drawing or multiple edges will appear
	#      in ancestors 
	# Assumptions: relies on accuracy of finding forks in self.record.blocks_by_forks - need to think about this more
	# second alternate method of drawing mainchain with forks is iterating and drawing all blocks at that height
	# bug to be fixed: when drawing epochs it draws two edges in mainchain 
	def draw_mainchain_with_forks_version_1(self):
		 
 
		for fork in self.record.blocks_by_forks:
			#Group forks so the edges are straight (prettier)
			self.g.body.append("node[group={}];".format(self.record.blocks_by_forks.index(fork)))
			self.draw_chain(fork['end'], fork['start'])
		
		self.g.node(self.mainchain_caption, shape='none')

		#draw justified blocks
		#for blocks in self.record.
	 
	def draw_mainchain(self, chain):
		
		self.draw_chain(chain.head, self.mainchain_genesis_header)
		self.g.node(self.mainchain_caption, shape='none')

	#TODO: review changes - an added function similar to sharding visualization draw_mainchain
	#	   except code moved into draw_chain. Removed first while loop (think it's a repeat of second while loop)
	def draw_chain(self, head_block, stop_block):
		# record the highest node name
		self.min_hash = self.get_node_name_from_hash(head_block.header.hash)
		tx_labels_in_current_period = []
		current_block_header = head_block.header

		#Loop from head of chain down to last block
		while (current_block_header is not None) and (current_block_header.hash != stop_block.header.prevhash):
			if current_block_header == self.record.mainchain_genesis_header:
				prev_block_header = None
				prev_block_hash = self.mainchain_caption
			else:
				prev_block_header = self.record.blocks[current_block_header.prevhash]
				prev_block_hash = prev_block_header.hash
				#aha kill me - below ensures checkpoints point to the same checkpoint in the previous epoch
				if self.draw_in_epoch and current_block_header.number % EPOCH_LENGTH == 0 and prev_block_header.number != 0:
					for distance in range(EPOCH_LENGTH - 1):
						prev_block_header = self.record.blocks[prev_block_header.prevhash]
						prev_block_hash = prev_block_header.hash

 
			label_edges = self.get_labels_from_node(current_block_header.hash)	
			current_epoch = current_block_header.number // EPOCH_LENGTH
			tx_labels_in_current_period = label_edges + tx_labels_in_current_period

			#draw epoch or block
			if not self.draw_in_epoch:
				self.draw_block(
					current_block_header.hash,
					prev_block_hash,
					label_edges,
					current_block_header.number,
                )
			elif current_block_header.number % EPOCH_LENGTH == 0:
				self.draw_block(
					current_block_header.hash,
					prev_block_hash,
					tx_labels_in_current_period,
					current_epoch,
				)
				tx_labels_in_current_period = []
				
			current_block_header = prev_block_header

	def draw_votes(self):
		
		self.g.body.append("node[group=votes];")

		#Draw each vote 
		for hash, votes in self.record.votes.items():
			for vote in votes: 
			 
				vote_name = self.get_node_name_from_hash(bytes([vote['index']]) + hash) #attempt to make each vote name unique by appending hash + voter_index
				source_epoch = vote['source'] 
				current_epoch = vote['target']
				caption = vote['index']

				self.g.node(vote_name, str(caption), shape='circle')
				
				block_target_name = self.get_node_name_from_hash(hash) 
				number_of_blocks_away = (current_epoch - source_epoch) * EPOCH_LENGTH
				
				#Grab block hash of source epoch
				source_block_header = self.record.blocks[hash]
				
				while number_of_blocks_away:
					source_block_header = self.record.blocks[source_block_header.prevhash]
					number_of_blocks_away -= 1
			
				block_source_name = self.get_node_name_from_hash(source_block_header.hash)
				height = 1

				if self.draw_in_epoch:
					block_target_header = self.record.blocks[hash]
					while block_target_header.number % EPOCH_LENGTH != 0:
						block_target_header = self.record.blocks[block_target_header.prevhash]
					while source_block_header.number % EPOCH_LENGTH != 0:
						source_block_header = self.record.blocks[source_block_header.prevhash]
					block_target_name = self.get_node_name_from_hash(block_target_header.hash) 
					block_source_name = self.get_node_name_from_hash(source_block_header.hash) 

				self.g.edge(vote_name, block_target_name)
				self.g.edge(vote_name, block_source_name)
				self.layers[block_target_name].append(vote_name)
				 


	def get_node_name_from_hash(self, node_hash):
		if self.draw_in_epoch and node_hash in self.record.blocks:
			#change: if drawing forks need unique epoch names 

			block_number = "{}{}".format(self.record.blocks[node_hash].number // EPOCH_LENGTH, get_shorten_hash(node_hash))
			

			return block_number

		if isinstance(node_hash, bytes):
			node_hash = get_shorten_hash(node_hash)
		return node_hash

	def get_labels_from_node(self, node_hash):
		label_obj_list = self.record.get_tx_labels_from_node(node_hash)
		node_name = self.get_node_name_from_hash(node_hash)
		labels = []
			 
		return labels

    #TODO: add the rest of the code from sharding viz
	def draw_struct(self, node_name, prev_node_name, height, label_edges, shape, caption):
		assert isinstance(height, int) #TODO: ask why assert height :p
		label_list = [item[0][1] for item in label_edges]
		struct_label = '{ %s }' % caption 
		self.g.node(node_name, struct_label, shape=shape)
		self.g.edge(node_name, prev_node_name)

	# Align the nodes on specific heights 
	def add_rank(self, node_list, rank='same'):
		rank_same_str = "\t{rank=%s; " % rank
		for node in node_list:
			rank_same_str += (self.g._quote(node) + '; ')
		rank_same_str += ' }'
		self.g.body.append(rank_same_str)


	def set_rank(self, layers):
		# set rank
		for period, labels in layers.items():
			rank = 'same'
			if period == self.min_hash:
				rank = 'source'
			elif period == self.mainchain_caption:
				rank = 'max'
			self.add_rank([period] + labels, rank)

	def draw(self):

		#self.draw_mainchain(self.mainchain) # This would be drawing sharding's visualization (only the main chain no forks)
		self.draw_mainchain_with_forks_version_1() # first version of drawing mainchain with forks
		
		self.draw_votes()
		
		self.set_rank(self.layers)
		
		self.g.render()
